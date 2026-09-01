"""In-memory lifecycle manager for the sole BUPT client in this local app."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable

from app.providers.bupt_auth import AuthErrorKind, AuthFailure
from app.providers.bupt_client import BUPTClient
from app.schemas.auth import SessionState, SessionStatus
from app.schemas.common import ApiResponse, ErrorCode
from app.services.auth_bootstrap import AppBusinessSession, AuthBootstrapService, BootstrapResult, create_runtime_client
from app.services.upstream_session_service import (
    UpstreamSessionConfigurationError,
    UpstreamSessionError,
    UpstreamSessionStatus,
)


@dataclass(frozen=True)
class SessionAccessError(Exception):
    code: ErrorCode
    message: str


class AuthSessionManager:
    """Own one in-memory BUPT session; credentials are never retained as state."""

    def __init__(
        self,
        bootstrap_service: AuthBootstrapService | None = None,
        runtime_client_factory: Callable[[AppBusinessSession], BUPTClient] | None = None,
        runtime_session_loader: Callable[[int], Awaitable[AppBusinessSession]] | None = None,
        runtime_cookie_persister: Callable[[int, BUPTClient], Awaitable[bool]] | None = None,
        runtime_marker: Callable[[int], Awaitable[None]] | None = None,
        runtime_expiry_marker: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        self._client: BUPTClient | None = None
        self._runtime_user_id: int | None = None
        self._lock = asyncio.Lock()
        self._bootstrap_service = bootstrap_service or AuthBootstrapService()
        self._runtime_client_factory = runtime_client_factory or create_runtime_client
        self._runtime_session_loader = runtime_session_loader
        self._runtime_cookie_persister = runtime_cookie_persister
        self._runtime_marker = runtime_marker
        self._runtime_expiry_marker = runtime_expiry_marker

    def get_client(self, user_id: int | None = None) -> BUPTClient | None:
        """Read the single transitional runtime only when it belongs to the requested user."""
        if user_id is not None and user_id != self._runtime_user_id:
            return None
        return self._client

    async def bootstrap_login(self, username: str, password: str) -> ApiResponse[BootstrapResult]:
        """Authenticate upstream without assigning that result to a local application user."""
        try:
            return ApiResponse.ok(await self._bootstrap_service.authenticate(username, password))
        except AuthFailure as exc:
            return ApiResponse.error(_login_error_code(exc), "authentication failed")
        except Exception:
            return ApiResponse.error(ErrorCode.INTERNAL_ERROR, "authentication could not be completed")

    async def activate_runtime(self, user_id: int, app_session: AppBusinessSession) -> ApiResponse[None]:
        """Set the transitional one-client cache from this user's already persisted session."""
        async with self._lock:
            try:
                client = self._runtime_client_factory(app_session)
            except Exception:
                return ApiResponse.error(ErrorCode.INTERNAL_ERROR, "runtime client could not be created")
            await self._clear_locked()
            self._client = client
            self._runtime_user_id = user_id
            return ApiResponse.ok(None, "runtime client activated")

    async def get_or_create_runtime_client(self, user_id: int) -> BUPTClient:
        """Future-shaped lookup without a multi-user client pool in B2.1."""
        async with self._lock:
            return await self._get_or_create_locked(user_id)

    async def logout(self) -> ApiResponse[SessionStatus]:
        """Close only this program's client; it never logs out browser-wide BUPT SSO."""
        async with self._lock:
            await self._clear_locked()
            return ApiResponse.ok(_unauthenticated_status(), "Logged out")

    async def status(self) -> ApiResponse[SessionStatus]:
        async with self._lock:
            if self._client is None:
                return ApiResponse.ok(_unauthenticated_status())
            verification = await self._client.check_auth_result()
            if verification.success:
                return ApiResponse.ok(_authenticated_status())
            if verification.code == ErrorCode.SESSION_EXPIRED:
                await self._clear_locked()
                return ApiResponse.ok(_expired_status(), "session expired; please log in again")
            return ApiResponse.error(verification.code, "session status could not be checked")

    @asynccontextmanager
    async def acquire_client(self, user_id: int | None = None) -> AsyncIterator[BUPTClient]:
        """Lease a user-addressed runtime; ``None`` is retained only for the unchanged single-user scheduler."""
        async with self._lock:
            client = self._client if user_id is None else await self._get_or_create_locked(user_id)
            if client is None:
                raise SessionAccessError(ErrorCode.AUTH_REQUIRED, "log in before accessing electricity data")
            verification = await client.check_auth_result()
            if not verification.success:
                if verification.code == ErrorCode.SESSION_EXPIRED:
                    if user_id is not None:
                        await self._mark_expired(user_id)
                    await self._clear_locked()
                    raise SessionAccessError(ErrorCode.SESSION_EXPIRED, "session expired; please log in again")
                raise SessionAccessError(verification.code, "session could not be checked")
            if user_id is not None:
                await self._mark_validated(user_id)
            try:
                yield client
            finally:
                if user_id is not None:
                    post_verification = await client.check_auth_result()
                    if post_verification.success:
                        await self._mark_validated(user_id)
                        await self._persist_runtime_cookies(user_id, client)
                    elif post_verification.code == ErrorCode.SESSION_EXPIRED:
                        await self._mark_expired(user_id)
                        if self._client is client:
                            await self._clear_locked()

    async def _get_or_create_locked(self, user_id: int) -> BUPTClient:
        if self._client is not None and self._runtime_user_id == user_id:
            return self._client
        if self._runtime_session_loader is None:
            raise SessionAccessError(ErrorCode.REAUTH_REQUIRED, "upstream session restoration is unavailable")
        try:
            app_session = await self._runtime_session_loader(user_id)
            client = self._runtime_client_factory(app_session)
        except UpstreamSessionConfigurationError as exc:
            raise SessionAccessError(ErrorCode.INTERNAL_ERROR, "upstream session encryption is not configured") from exc
        except UpstreamSessionError as exc:
            code = ErrorCode.REAUTH_REQUIRED if exc.status == UpstreamSessionStatus.REAUTH_REQUIRED else ErrorCode.SESSION_EXPIRED
            raise SessionAccessError(code, "upstream session requires reauthentication") from exc
        except Exception as exc:
            raise SessionAccessError(ErrorCode.INTERNAL_ERROR, "runtime client could not be restored") from exc
        await self._clear_locked()
        self._client = client
        self._runtime_user_id = user_id
        return client

    async def _persist_runtime_cookies(self, user_id: int, client: BUPTClient) -> None:
        if self._runtime_cookie_persister is None:
            return
        try:
            await self._runtime_cookie_persister(user_id, client)
        except UpstreamSessionError as exc:
            if exc.status == UpstreamSessionStatus.EXPIRED:
                await self._mark_expired(user_id)
            return
        except UpstreamSessionConfigurationError:
            # The client remains usable for this completed request; a later restore will require reauthentication.
            return

    async def _mark_validated(self, user_id: int) -> None:
        if self._runtime_marker is not None:
            await self._runtime_marker(user_id)

    async def _mark_expired(self, user_id: int) -> None:
        if self._runtime_expiry_marker is not None:
            await self._runtime_expiry_marker(user_id)

    async def _clear_locked(self) -> None:
        client, self._client = self._client, None
        self._runtime_user_id = None
        if client is not None:
            await client.close()


def _authenticated_status() -> SessionStatus:
    return SessionStatus(authenticated=True, state=SessionState.AUTHENTICATED)


def _unauthenticated_status() -> SessionStatus:
    return SessionStatus(authenticated=False, state=SessionState.UNAUTHENTICATED)


def _expired_status() -> SessionStatus:
    return SessionStatus(authenticated=False, state=SessionState.SESSION_EXPIRED)


def _login_error_code(error: AuthFailure) -> ErrorCode:
    if error.kind == AuthErrorKind.TIMEOUT:
        return ErrorCode.TIMEOUT
    if error.kind == AuthErrorKind.NETWORK_ERROR:
        return ErrorCode.NETWORK_ERROR
    return ErrorCode.AUTH_FAILED
