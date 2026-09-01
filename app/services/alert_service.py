"""User-scoped idempotent alert lifecycle evaluation."""
from __future__ import annotations
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.alert import AlertSettings
from app.repositories.alert_repository import AlertRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import AlertEventRead, AlertEventStatus, AlertLevel, AlertSettingsRead, AlertSettingsUpdate, AlertType, ElectricityReading
from app.services.electricity_service import local_now, parse_source_time
from app.services.statistics_service import StatisticsService

class AlertService:
    def __init__(self, session: AsyncSession) -> None: self._session,self._repo=session,AlertRepository(session)
    async def get_settings(self,user_id:int)->ApiResponse[AlertSettingsRead]:
        try:
            value=await self._repo.get_settings(user_id,local_now()); await self._session.commit(); return ApiResponse.ok(AlertSettingsRead.model_validate(value,from_attributes=True))
        except SQLAlchemyError: await self._session.rollback(); return ApiResponse.error(ErrorCode.DATABASE_ERROR,"alert settings could not be read")
    async def save_settings(self,user_id:int,payload:AlertSettingsUpdate)->ApiResponse[AlertSettingsRead]:
        try:
            value=await self._repo.update_settings(user_id,payload,local_now()); await self._session.commit(); return ApiResponse.ok(AlertSettingsRead.model_validate(value,from_attributes=True))
        except SQLAlchemyError: await self._session.rollback(); return ApiResponse.error(ErrorCode.DATABASE_ERROR,"alert settings could not be saved")
    async def list_events(self,user_id:int,area_id:str,room_id:str,status:AlertEventStatus|None,limit:int)->ApiResponse[list[AlertEventRead]]:
        try:return ApiResponse.ok([AlertEventRead.model_validate(x) for x in await self._repo.list(user_id,area_id,room_id,status,limit)])
        except SQLAlchemyError:return ApiResponse.error(ErrorCode.DATABASE_ERROR,"alerts could not be read")
    async def evaluate(self,user_id:int,reading:ElectricityReading)->None:
        try:
            settings=await self._repo.get_settings(user_id,local_now())
            if settings.enabled:
                await self._evaluate_value(user_id,reading,settings,AlertType.LOW_BALANCE,reading.remaining_money,settings.low_balance_enabled,settings.balance_warning_threshold,settings.balance_critical_threshold)
                analysis=await StatisticsService(self._session).get_analysis(area_id=reading.area_id,room_id=reading.room_id)
                days=analysis.data.prediction.estimated_remaining_days if analysis.success and analysis.data else None
                await self._evaluate_value(user_id,reading,settings,AlertType.LOW_REMAINING_DAYS,days,settings.low_remaining_days_enabled,settings.remaining_days_warning_threshold,settings.remaining_days_critical_threshold)
            await self._session.commit()
        except SQLAlchemyError: await self._session.rollback()
    async def _evaluate_value(self,user_id:int,r:ElectricityReading,s:AlertSettings,k:AlertType,v:float|None,enabled:bool,w:float,c:float)->None:
        if not enabled or v is None:return
        active=await self._repo.get_active(user_id,r.area_id,r.room_id,k); level=AlertLevel.CRITICAL if v<=c else AlertLevel.WARNING if v<=w else None; now=local_now()
        if level is None:
            if active: active.status=AlertEventStatus.RESOLVED.value; active.resolved_at=active.last_seen_at=active.updated_at=now
            return
        threshold=c if level==AlertLevel.CRITICAL else w; title="余额不足" if k==AlertType.LOW_BALANCE else "预计可用时间较短"; unit="元" if k==AlertType.LOW_BALANCE else "天"; msg=f"{title}：当前 {v:.2f} {unit}，阈值 {threshold:.2f} {unit}"
        if active:
            active.level,active.trigger_value,active.threshold_value=level.value,v,threshold; active.title,active.message,active.source_time,active.last_seen_at,active.updated_at=title,msg,parse_source_time(r.source_time),now,now; return
        await self._repo.create(user_id=user_id,area_id=r.area_id,room_id=r.room_id,building_name=r.building_name,floor_name=r.floor_name,room_name=r.room_name,alert_type=k.value,level=level.value,status=AlertEventStatus.ACTIVE.value,title=title,message=msg,trigger_value=v,threshold_value=threshold,source_time=parse_source_time(r.source_time),first_triggered_at=now,last_seen_at=now,resolved_at=None,created_at=now,updated_at=now)
