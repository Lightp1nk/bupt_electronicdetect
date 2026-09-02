"""Business flow from a live upstream reading to a durable history snapshot."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_providers.electricity import ElectricityDataProvider, RealElectricityDataProvider
from app.models.electricity import ElectricityRecord
from app.providers.bupt_client import BUPTClient
from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import ElectricityQuerySaveResult, ElectricityReading, ElectricityRecordRead


BEIJING_TZ = ZoneInfo("Asia/Shanghai")


class ElectricityService:
    """Coordinates provider reads and snapshot persistence; it owns commit/rollback."""

    def __init__(self, session: AsyncSession, *, read_provider: ElectricityDataProvider | None = None) -> None:
        self._session = session
        self._repository = ElectricityRepository(session)
        self._read_provider = read_provider or RealElectricityDataProvider(session)

    async def query_and_save(
        self,
        client: BUPTClient,
        *,
        area_id: str,
        building_id: str,
        floor_id: str,
        room_id: str,
        room_name: str | None = None,
    ) -> ApiResponse[ElectricityQuerySaveResult]:
        upstream = await client.query_electricity(
            area_id=area_id,
            building_id=building_id,
            floor_id=floor_id,
            room_id=room_id,
            room_name=room_name,
        )
        if not upstream.success or upstream.data is None:
            return ApiResponse.error(upstream.code, upstream.message)

        reading = upstream.data
        source_time = parse_source_time(reading.source_time)
        query_time = local_now()
        try:
            if source_time is not None:
                existing = await self._repository.get_by_source_time(reading.area_id, reading.room_id, source_time)
                if existing is not None:
                    return ApiResponse.ok(
                        ElectricityQuerySaveResult(
                            reading=reading,
                            record=record_to_read(existing),
                            saved=False,
                            duplicate=True,
                        ),
                        "duplicate upstream snapshot was not inserted",
                    )
            record = await self._repository.add(reading, source_time=source_time, query_time=query_time)
            await self._session.commit()
            return ApiResponse.ok(
                ElectricityQuerySaveResult(reading=reading, record=record_to_read(record), saved=True, duplicate=False),
                "electricity snapshot saved",
            )
        except IntegrityError:
            await self._session.rollback()
            # A concurrent request can win after the explicit pre-insert lookup.
            if source_time is not None:
                existing = await self._repository.get_by_source_time(reading.area_id, reading.room_id, source_time)
                if existing is not None:
                    return ApiResponse.ok(
                        ElectricityQuerySaveResult(
                            reading=reading,
                            record=record_to_read(existing),
                            saved=False,
                            duplicate=True,
                        ),
                        "duplicate upstream snapshot was not inserted",
                    )
            return ApiResponse.error(ErrorCode.DATABASE_ERROR, "snapshot could not be saved")
        except SQLAlchemyError:
            await self._session.rollback()
            return ApiResponse.error(ErrorCode.DATABASE_ERROR, "snapshot could not be saved")

    async def get_history(
        self, *, area_id: str, room_id: str, days: int | None = None, limit: int | None = None
    ) -> ApiResponse[list[ElectricityRecordRead]]:
        if not area_id or not room_id:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, "area_id and room_id are required")
        if days is not None and days <= 0:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, "days must be positive")
        if limit is not None and limit <= 0:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, "limit must be positive")
        since = local_now() - timedelta(days=days) if days is not None else None
        try:
            records = await self._read_provider.get_history(area_id, room_id, since=since, limit=limit)
            return ApiResponse.ok(list(records))
        except SQLAlchemyError:
            return ApiResponse.error(ErrorCode.DATABASE_ERROR, "history could not be read")

    async def get_latest(self, *, area_id: str, room_id: str) -> ApiResponse[ElectricityRecordRead]:
        if not area_id or not room_id:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, "area_id and room_id are required")
        try:
            record = await self._read_provider.get_latest(area_id, room_id)
            if record is None:
                return ApiResponse.error(ErrorCode.NOT_FOUND, "no saved electricity history for this room")
            return ApiResponse.ok(record)
        except SQLAlchemyError:
            return ApiResponse.error(ErrorCode.DATABASE_ERROR, "latest record could not be read")


def local_now() -> datetime:
    """Persist local China time as a consistently naive SQLite datetime."""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def parse_source_time(value: str | None) -> datetime | None:
    """Parse upstream local time; unknown/missing formats are intentionally not deduplicated."""
    if not value or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(BEIJING_TZ).replace(tzinfo=None)
    return parsed


def record_to_read(record: ElectricityRecord) -> ElectricityRecordRead:
    return ElectricityRecordRead.model_validate(record)
