"""Encrypted storage and runtime restoration for BUPT app-domain business sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.upstream_session import UpstreamSession
from app.providers.bupt_client import BUPTClient
from app.repositories.upstream_session_repository import UpstreamSessionRepository
from app.services.app_session_service import utc_now
from app.services.auth_bootstrap import AppBusinessSession


class UpstreamSessionStatus:
    UNKNOWN = "UNKNOWN"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"


class UpstreamSessionError(Exception):
    """Safe category-only error: never carry a cookie, key, or ciphertext."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(status)


class UpstreamSessionConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class UpstreamSessionCipher:
    _fernet: Fernet

    @classmethod
    def from_environment(cls) -> "UpstreamSessionCipher":
        value = os.getenv("APP_UPSTREAM_SESSION_KEY")
        if not value:
            raise UpstreamSessionConfigurationError("upstream session encryption is not configured")
        try:
            return cls(Fernet(value.encode("ascii")))
        except (ValueError, TypeError) as exc:
            raise UpstreamSessionConfigurationError("upstream session encryption key is invalid") from exc

    def encrypt(self, app_session: AppBusinessSession) -> str:
        payload = json.dumps(app_session.to_payload(), separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(payload).decode("ascii")

    def decrypt(self, encrypted_blob: str) -> AppBusinessSession:
        try:
            payload = json.loads(self._fernet.decrypt(encrypted_blob.encode("ascii")).decode("utf-8"))
            return AppBusinessSession.from_payload(payload)
        except (InvalidToken, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise UpstreamSessionError(UpstreamSessionStatus.EXPIRED) from exc


class UpstreamSessionService:
    """Own encrypted session serialization; never expose raw Cookie values to routes or logs."""

    def __init__(self, session_factory: Callable[[], AsyncSession]) -> None:
        self._session_factory = session_factory
        self._cipher: UpstreamSessionCipher | None = None

    def _get_cipher(self) -> UpstreamSessionCipher:
        if self._cipher is None:
            self._cipher = UpstreamSessionCipher.from_environment()
        return self._cipher

    async def save_authenticated_session(
        self, session: AsyncSession, *, user_id: int, app_session: AppBusinessSession, now: datetime,
    ) -> UpstreamSession:
        encrypted_blob = self._get_cipher().encrypt(app_session)
        return await UpstreamSessionRepository(session).create_or_update(
            user_id=user_id,
            encrypted_cookie_blob=encrypted_blob,
            status=UpstreamSessionStatus.ACTIVE,
            now=now,
            last_validated_at=now,
        )

    async def get_status(self, session: AsyncSession, user_id: int) -> str:
        record = await UpstreamSessionRepository(session).get_by_user_id(user_id)
        return record.status if record is not None else UpstreamSessionStatus.REAUTH_REQUIRED

    async def load_business_session(self, user_id: int) -> AppBusinessSession:
        async with self._session_factory() as session:
            repository = UpstreamSessionRepository(session)
            record = await repository.get_by_user_id(user_id)
            if record is None:
                raise UpstreamSessionError(UpstreamSessionStatus.REAUTH_REQUIRED)
            if record.status in {UpstreamSessionStatus.EXPIRED, UpstreamSessionStatus.REAUTH_REQUIRED}:
                raise UpstreamSessionError(record.status)
            try:
                return self._get_cipher().decrypt(record.encrypted_cookie_blob)
            except UpstreamSessionError:
                await repository.mark_status(user_id, status=UpstreamSessionStatus.EXPIRED, now=utc_now())
                await session.commit()
                raise
            except UpstreamSessionConfigurationError:
                raise
            except SQLAlchemyError as exc:
                await session.rollback()
                raise UpstreamSessionError(UpstreamSessionStatus.UNKNOWN) from exc

    async def persist_runtime_cookies(self, user_id: int, client: BUPTClient) -> bool:
        """Re-encrypt only if the business-cookie snapshot changed during a Runtime lease."""
        try:
            app_session = AppBusinessSession.from_cookiejar(client.client.cookies.jar)
        except ValueError as exc:
            raise UpstreamSessionError(UpstreamSessionStatus.EXPIRED) from exc
        async with self._session_factory() as session:
            repository = UpstreamSessionRepository(session)
            record = await repository.get_by_user_id(user_id)
            if record is None:
                raise UpstreamSessionError(UpstreamSessionStatus.REAUTH_REQUIRED)
            cipher = self._get_cipher()
            changed = True
            try:
                changed = cipher.decrypt(record.encrypted_cookie_blob) != app_session
            except UpstreamSessionError:
                changed = True
            if changed:
                await repository.create_or_update(
                    user_id=user_id,
                    encrypted_cookie_blob=cipher.encrypt(app_session),
                    status=UpstreamSessionStatus.ACTIVE,
                    now=utc_now(),
                    last_validated_at=utc_now(),
                )
                await session.commit()
            return changed

    async def mark_expired(self, user_id: int) -> None:
        async with self._session_factory() as session:
            try:
                await UpstreamSessionRepository(session).mark_status(
                    user_id, status=UpstreamSessionStatus.EXPIRED, now=utc_now(),
                )
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()

    async def mark_validated(self, user_id: int) -> None:
        async with self._session_factory() as session:
            try:
                await UpstreamSessionRepository(session).mark_active(user_id, now=utc_now())
                await session.commit()
            except SQLAlchemyError:
                await session.rollback()
