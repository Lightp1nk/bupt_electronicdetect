"""Data access for idempotent notification delivery stages."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_binding import NotificationBinding
from app.models.notification_delivery import NotificationDelivery


class NotificationDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, event_id: int, binding_id: int, provider: str, stage: str) -> NotificationDelivery | None:
        return await self._session.scalar(select(NotificationDelivery).where(
            NotificationDelivery.alert_event_id == event_id,
            NotificationDelivery.binding_id == binding_id,
            NotificationDelivery.provider == provider,
            NotificationDelivery.stage == stage,
        ))

    async def create_pending(self, *, event_id: int, binding_id: int, provider: str, stage: str, now: datetime) -> NotificationDelivery:
        value = NotificationDelivery(
            alert_event_id=event_id, binding_id=binding_id, provider=provider, stage=stage,
            status="pending", created_at=now, sent_at=None, error_message=None,
        )
        self._session.add(value)
        await self._session.flush()
        return value

    async def latest_for_user(self, user_id: int) -> NotificationDelivery | None:
        stmt = (
            select(NotificationDelivery)
            .join_from(NotificationDelivery, NotificationBinding)
            .where(NotificationBinding.user_id == user_id)
            .order_by(NotificationDelivery.created_at.desc(), NotificationDelivery.id.desc())
            .limit(1)
        )
        return await self._session.scalar(stmt)
