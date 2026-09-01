"""Idempotent alert-event lifecycle evaluation; no provider calls occur here."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import AlertSettings
from app.repositories.alert_repository import AlertRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import AlertEventRead, AlertEventStatus, AlertLevel, AlertSettingsRead, AlertSettingsUpdate, AlertType, ElectricityReading
from app.services.electricity_service import local_now, parse_source_time
from app.services.statistics_service import StatisticsService

class AlertService:
    def __init__(self, session: AsyncSession) -> None: self._session, self._repo = session, AlertRepository(session)
    async def get_settings(self) -> ApiResponse[AlertSettingsRead]:
        try:
            value = await self._repo.get_current_settings(); await self._session.commit(); return ApiResponse.ok(AlertSettingsRead.model_validate(value, from_attributes=True))
        except SQLAlchemyError: await self._session.rollback(); return ApiResponse.error(ErrorCode.DATABASE_ERROR, "alert settings could not be read")
    async def save_settings(self, payload: AlertSettingsUpdate) -> ApiResponse[AlertSettingsRead]:
        try:
            value = await self._repo.update_current_settings(payload); await self._session.commit(); return ApiResponse.ok(AlertSettingsRead.model_validate(value, from_attributes=True))
        except SQLAlchemyError: await self._session.rollback(); return ApiResponse.error(ErrorCode.DATABASE_ERROR, "alert settings could not be saved")
    async def list_events(self, area_id: str, room_id: str, status: AlertEventStatus | None, limit: int) -> ApiResponse[list[AlertEventRead]]:
        try: return ApiResponse.ok([AlertEventRead.model_validate(x) for x in await self._repo.list(area_id, room_id, status, limit)])
        except SQLAlchemyError: return ApiResponse.error(ErrorCode.DATABASE_ERROR, "alerts could not be read")
    async def evaluate(self, reading: ElectricityReading) -> None:
        """Evaluate after a committed real query; failures never invalidate that query."""
        try:
            settings = await self._repo.get_current_settings()
            if not settings.enabled: await self._session.commit(); return
            await self._evaluate_value(reading, settings, AlertType.LOW_BALANCE, reading.remaining_money, settings.low_balance_enabled, settings.balance_warning_threshold, settings.balance_critical_threshold)
            analysis = await StatisticsService(self._session).get_analysis(area_id=reading.area_id, room_id=reading.room_id)
            days = analysis.data.prediction.estimated_remaining_days if analysis.success and analysis.data else None
            await self._evaluate_value(reading, settings, AlertType.LOW_REMAINING_DAYS, days, settings.low_remaining_days_enabled, settings.remaining_days_warning_threshold, settings.remaining_days_critical_threshold)
            await self._session.commit()
        except SQLAlchemyError: await self._session.rollback()
    async def _evaluate_value(self, reading: ElectricityReading, settings: AlertSettings, kind: AlertType, value: float | None, enabled: bool, warning: float, critical: float) -> None:
        if not enabled or value is None: return  # disabled/unknown never mutate an episode
        active = await self._repo.get_active(reading.area_id, reading.room_id, kind)
        level = AlertLevel.CRITICAL if value <= critical else AlertLevel.WARNING if value <= warning else None
        now, source = local_now(), parse_source_time(reading.source_time)
        if level is None:
            if active:
                active.status = AlertEventStatus.RESOLVED.value; active.resolved_at = now; active.updated_at = now; active.last_seen_at = now
                active.message = "当前余额已恢复至正常范围" if kind == AlertType.LOW_BALANCE else "预计可用时间已恢复至正常范围"
            return
        threshold = critical if level == AlertLevel.CRITICAL else warning
        title = "余额不足" if kind == AlertType.LOW_BALANCE else "预计可用时间较短"
        unit = "元" if kind == AlertType.LOW_BALANCE else "天"
        message = f"{title}：当前 {value:.2f} {unit}，阈值 {threshold:.2f} {unit}"
        if active:
            active.level, active.trigger_value, active.threshold_value = level.value, value, threshold
            active.title, active.message, active.source_time, active.last_seen_at, active.updated_at = title, message, source, now, now
            return
        await self._repo.create(area_id=reading.area_id, room_id=reading.room_id, building_name=reading.building_name, floor_name=reading.floor_name, room_name=reading.room_name, alert_type=kind.value, level=level.value, status=AlertEventStatus.ACTIVE.value, title=title, message=message, trigger_value=value, threshold_value=threshold, source_time=source, first_triggered_at=now, last_seen_at=now, resolved_at=None, created_at=now, updated_at=now)
