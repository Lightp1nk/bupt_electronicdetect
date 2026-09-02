"""Read-only electricity summaries for a verified chat identity."""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.chat_identity_repository import ChatIdentityRepository
from app.repositories.collection_repository import CollectionRepository
from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.chat import ChatElectricitySummaryRead, ChatPlatform
from app.schemas.common import ApiResponse, ErrorCode
from app.services.statistics_service import StatisticsService


class ChatElectricitySummaryService:
    """Resolve QQ identity → User → configured room → saved snapshot only.

    This service deliberately never receives a Runtime Client and therefore
    cannot perform an upstream BUPT electricity request.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._identities = ChatIdentityRepository(session)
        self._collections = CollectionRepository(session)
        self._electricity = ElectricityRepository(session)

    async def get_summary(self, platform: ChatPlatform, external_id: str) -> ApiResponse[ChatElectricitySummaryRead]:
        try:
            identity = await self._identities.get_by_external_id(platform.value, external_id)
            if identity is None:
                return ApiResponse.error(ErrorCode.CHAT_NOT_BOUND, "chat identity is not bound")
            settings = await self._collections.get_settings(identity.user_id)
            if settings is None or not all((settings.area_id, settings.building_id, settings.floor_id, settings.room_id)):
                return ApiResponse.error(ErrorCode.NO_ROOM_CONFIGURED, "no monitored room is configured")

            latest = await self._electricity.get_latest(settings.area_id, settings.room_id)
            if latest is None:
                return ApiResponse.error(ErrorCode.NO_DATA, "no saved electricity snapshot is available")
            analysis = await StatisticsService(self._session).get_analysis(area_id=settings.area_id, room_id=settings.room_id)
            if not analysis.success or analysis.data is None:
                return ApiResponse.error(ErrorCode.NO_DATA, "no saved electricity snapshot is available")

            room_parts = [settings.area_name, settings.building_name, settings.floor_name, settings.room_name]
            room_name = " · ".join(part for part in room_parts if part) or latest.room_name or "已配置宿舍"
            return ApiResponse.ok(ChatElectricitySummaryRead(
                room_name=room_name,
                balance=latest.remaining_money,
                remaining_kwh=latest.remaining_kwh,
                total_usage_kwh=latest.total_usage_kwh,
                source_time=latest.source_time,
                estimated_remaining_days=analysis.data.prediction.estimated_remaining_days,
                maturity=analysis.data.prediction.maturity.value,
            ))
        except SQLAlchemyError:
            return ApiResponse.error(ErrorCode.DATABASE_ERROR, "electricity summary could not be read")
