"""Data access for encrypted per-user upstream business sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.upstream_session import UpstreamSession


class UpstreamSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> UpstreamSession | None:
        return await self._session.scalar(select(UpstreamSession).where(UpstreamSession.user_id == user_id))

    async def create_or_update(
        self, *, user_id: int, encrypted_cookie_blob: str, status: str, now: datetime, last_validated_at: datetime | None,
    ) -> UpstreamSession:
        record = await self.get_by_user_id(user_id)
        if record is None:
            record = UpstreamSession(
                user_id=user_id,
                encrypted_cookie_blob=encrypted_cookie_blob,
                status=status,
                last_validated_at=last_validated_at,
                created_at=now,
                updated_at=now,
            )
            self._session.add(record)
            await self._session.flush()
        else:
            record.encrypted_cookie_blob = encrypted_cookie_blob
            record.status = status
            record.last_validated_at = last_validated_at
            record.updated_at = now
        return record

    async def mark_status(self, user_id: int, *, status: str, now: datetime) -> bool:
        record = await self.get_by_user_id(user_id)
        if record is None:
            return False
        record.status = status
        record.updated_at = now
        return True

    async def mark_active(self, user_id: int, *, now: datetime) -> bool:
        record = await self.get_by_user_id(user_id)
        if record is None:
            return False
        record.status = "ACTIVE"
        record.last_validated_at = now
        record.updated_at = now
        return True

    async def delete(self, user_id: int) -> bool:
        record = await self.get_by_user_id(user_id)
        if record is None:
            return False
        await self._session.delete(record)
        return True
