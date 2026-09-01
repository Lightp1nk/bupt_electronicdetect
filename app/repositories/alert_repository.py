from __future__ import annotations
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import AlertEvent, AlertSettings
from app.schemas.electricity import AlertEventStatus, AlertLevel, AlertSettingsUpdate, AlertType

class AlertRepository:
    def __init__(self, session: AsyncSession) -> None: self._session = session
    async def get_current_settings(self) -> AlertSettings:
        value = await self._session.get(AlertSettings, 1)
        if value is None: value = AlertSettings(id=1); self._session.add(value); await self._session.flush()
        return value
    async def update_current_settings(self, payload: AlertSettingsUpdate) -> AlertSettings:
        value = await self.get_current_settings()
        for key, item in payload.model_dump().items(): setattr(value, key, item)
        return value
    async def get_active(self, area_id: str, room_id: str, alert_type: AlertType) -> AlertEvent | None:
        return await self._session.scalar(select(AlertEvent).where(AlertEvent.area_id == area_id, AlertEvent.room_id == room_id, AlertEvent.alert_type == alert_type.value, AlertEvent.status == AlertEventStatus.ACTIVE.value))
    async def create(self, **values: object) -> AlertEvent:
        event = AlertEvent(**values); self._session.add(event); await self._session.flush(); return event
    async def list(self, area_id: str, room_id: str, status: AlertEventStatus | None, limit: int) -> list[AlertEvent]:
        stmt = select(AlertEvent).where(AlertEvent.area_id == area_id, AlertEvent.room_id == room_id)
        if status is not None: stmt = stmt.where(AlertEvent.status == status.value)
        stmt = stmt.order_by(AlertEvent.last_seen_at.desc(), AlertEvent.id.desc()).limit(limit)
        return list((await self._session.scalars(stmt)).all())
