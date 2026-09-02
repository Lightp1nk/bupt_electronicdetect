"""Persistence for verified chat identities and short-lived binding codes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_identity import ChatIdentity, PendingChatBinding


class ChatIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_identity(self, user_id: int, platform: str) -> ChatIdentity | None:
        return await self._session.scalar(select(ChatIdentity).where(ChatIdentity.user_id == user_id, ChatIdentity.platform == platform))

    async def get_by_external_id(self, platform: str, external_id: str) -> ChatIdentity | None:
        return await self._session.scalar(select(ChatIdentity).where(ChatIdentity.platform == platform, ChatIdentity.external_id == external_id))

    async def save_identity(self, user_id: int, platform: str, external_id: str, now: datetime) -> ChatIdentity:
        identity = await self.get_identity(user_id, platform)
        if identity is None:
            identity = ChatIdentity(
                user_id=user_id, platform=platform, external_id=external_id,
                verified_at=now, created_at=now, updated_at=now,
            )
            self._session.add(identity)
        else:
            identity.external_id = external_id
            identity.verified_at = now
            identity.updated_at = now
        await self._session.flush()
        return identity

    async def delete_identity(self, user_id: int, platform: str) -> bool:
        identity = await self.get_identity(user_id, platform)
        if identity is None:
            return False
        await self._session.delete(identity)
        return True

    async def expire_pending_for_user(self, user_id: int, platform: str, now: datetime) -> None:
        await self._session.execute(
            update(PendingChatBinding)
            .where(PendingChatBinding.user_id == user_id, PendingChatBinding.platform == platform, PendingChatBinding.status == "pending")
            .values(status="expired")
        )

    async def create_pending(self, user_id: int, platform: str, code_hash: str, expires_at: datetime, now: datetime) -> PendingChatBinding:
        pending = PendingChatBinding(
            user_id=user_id, platform=platform, code_hash=code_hash, status="pending", expires_at=expires_at, created_at=now,
        )
        self._session.add(pending)
        await self._session.flush()
        return pending

    async def get_pending_by_code_hash(self, code_hash: str) -> PendingChatBinding | None:
        return await self._session.scalar(select(PendingChatBinding).where(PendingChatBinding.code_hash == code_hash))

    @staticmethod
    def mark_pending_expired(pending: PendingChatBinding) -> None:
        pending.status = "expired"

    @staticmethod
    def mark_pending_used(pending: PendingChatBinding, now: datetime) -> None:
        pending.status = "used"
        pending.used_at = now
