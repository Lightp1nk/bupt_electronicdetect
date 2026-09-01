from __future__ import annotations
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import AlertEvent, AlertSettings
from app.schemas.electricity import AlertEventStatus, AlertSettingsUpdate, AlertType

class AlertRepository:
    def __init__(self, session: AsyncSession) -> None: self._session = session
    async def get_settings(self, user_id: int, now: datetime) -> AlertSettings:
        value = await self._session.scalar(select(AlertSettings).where(AlertSettings.user_id == user_id))
        if value is None:
            value = AlertSettings(user_id=user_id, created_at=now, updated_at=now); self._session.add(value); await self._session.flush()
        return value
    async def update_settings(self, user_id: int, payload: AlertSettingsUpdate, now: datetime) -> AlertSettings:
        value = await self.get_settings(user_id, now)
        for key, item in payload.model_dump().items(): setattr(value, key, item)
        value.updated_at = now; return value
    async def get_active(self, user_id: int, area_id: str, room_id: str, kind: AlertType) -> AlertEvent | None:
        return await self._session.scalar(select(AlertEvent).where(AlertEvent.user_id==user_id, AlertEvent.area_id==area_id, AlertEvent.room_id==room_id, AlertEvent.alert_type==kind.value, AlertEvent.status==AlertEventStatus.ACTIVE.value))
    async def create(self, **values: object) -> AlertEvent:
        value=AlertEvent(**values); self._session.add(value); await self._session.flush(); return value
    async def list(self, user_id: int, area_id: str, room_id: str, status: AlertEventStatus | None, limit: int) -> list[AlertEvent]:
        stmt=select(AlertEvent).where(AlertEvent.user_id==user_id, AlertEvent.area_id==area_id, AlertEvent.room_id==room_id)
        if status: stmt=stmt.where(AlertEvent.status==status.value)
        return list((await self._session.scalars(stmt.order_by(AlertEvent.last_seen_at.desc(), AlertEvent.id.desc()).limit(limit))).all())
