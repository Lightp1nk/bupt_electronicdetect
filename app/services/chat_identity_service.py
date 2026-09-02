"""Issue one-time binding codes and confirm a platform identity without storing UMO data."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.chat_identity_repository import ChatIdentityRepository
from app.schemas.chat import ChatBindingCodeRead, ChatIdentityRead, ChatPlatform
from app.schemas.common import ApiResponse, ErrorCode
from app.services.app_session_service import utc_now


CODE_TTL = timedelta(minutes=10)
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 10


class ChatIdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = ChatIdentityRepository(session)

    async def get_identity(self, user_id: int, platform: ChatPlatform) -> ApiResponse[ChatIdentityRead | None]:
        identity = await self._repository.get_identity(user_id, platform.value)
        return ApiResponse.ok(ChatIdentityRead.model_validate(identity) if identity is not None else None)

    async def create_binding_code(self, user_id: int, platform: ChatPlatform) -> ApiResponse[ChatBindingCodeRead]:
        now = utc_now()
        code = self._new_code()
        await self._repository.expire_pending_for_user(user_id, platform.value, now)
        await self._repository.create_pending(user_id, platform.value, self._hash_code(code), now + CODE_TTL, now)
        await self._session.commit()
        return ApiResponse.ok(ChatBindingCodeRead(code=self._format_code(code), expires_at=now + CODE_TTL), "binding code created")

    async def delete_identity(self, user_id: int, platform: ChatPlatform) -> ApiResponse[None]:
        deleted = await self._repository.delete_identity(user_id, platform.value)
        await self._session.commit()
        if not deleted:
            return ApiResponse.error(ErrorCode.NOT_FOUND, "chat identity is not bound")
        return ApiResponse.ok(None, "chat identity removed")

    async def confirm_binding(self, platform: ChatPlatform, external_id: str, code: str) -> ApiResponse[ChatIdentityRead]:
        now = utc_now()
        pending = await self._repository.get_pending_by_code_hash(self._hash_code(self._normalize_code(code)))
        if pending is None or pending.platform != platform.value or pending.status != "pending":
            return ApiResponse.error(ErrorCode.AUTH_FAILED, "binding code is invalid or expired")
        if pending.expires_at <= now:
            self._repository.mark_pending_expired(pending)
            await self._session.commit()
            return ApiResponse.error(ErrorCode.AUTH_FAILED, "binding code is invalid or expired")

        owner = await self._repository.get_by_external_id(platform.value, external_id)
        if owner is not None and owner.user_id != pending.user_id:
            return ApiResponse.error(ErrorCode.BUSINESS_ERROR, "QQ identity is already bound")

        identity = await self._repository.save_identity(pending.user_id, platform.value, external_id, now)
        self._repository.mark_pending_used(pending, now)
        await self._session.commit()
        return ApiResponse.ok(ChatIdentityRead.model_validate(identity), "chat identity bound")

    @staticmethod
    def _new_code() -> str:
        return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))

    @staticmethod
    def _normalize_code(code: str) -> str:
        return code.replace("-", "").upper()

    @classmethod
    def _format_code(cls, code: str) -> str:
        normalized = cls._normalize_code(code)
        return f"{normalized[:5]}-{normalized[5:]}"

    @classmethod
    def _hash_code(cls, code: str) -> str:
        return hashlib.sha256(cls._normalize_code(code).encode("ascii")).hexdigest()
