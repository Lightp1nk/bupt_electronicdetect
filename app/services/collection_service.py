"""Single-process automatic collection orchestration using existing query/save logic."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import CollectionSettings
from app.repositories.collection_repository import CollectionRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import CollectionSettingsUpdate, CollectionStatus, CollectionStatusRead
from app.services.auth_session import AuthSessionManager, SessionAccessError
from app.services.electricity_service import ElectricityService, local_now, parse_source_time
from app.services.monitoring_service import MonitoringService


class CollectionService:
    """Serializes manual and scheduled collection runs for the single FastAPI process."""

    def __init__(
        self, session_factory: Callable[[], AsyncSession], auth_manager: AuthSessionManager, monitoring_service: MonitoringService,
        *, enabled: bool, hour: int, minute: int, lock: asyncio.Lock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._auth_manager = auth_manager
        self._monitoring_service = monitoring_service
        self._enabled, self._hour, self._minute = enabled, hour, minute
        self._lock = lock or asyncio.Lock()

    async def get_status(self, *, already_running: bool = False) -> ApiResponse[CollectionStatusRead]:
        async with self._session_factory() as session:
            try:
                settings = await CollectionRepository(session).get_current_settings()
                await session.commit()
                return ApiResponse.ok(self._to_read(settings, already_running=already_running))
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection status could not be read")

    async def save_settings(self, payload: CollectionSettingsUpdate) -> ApiResponse[CollectionStatusRead]:
        async with self._session_factory() as session:
            try:
                settings = await CollectionRepository(session).update_current_room(**payload.model_dump())
                await session.commit()
                return ApiResponse.ok(self._to_read(settings), "collection settings saved")
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection settings could not be saved")

    async def clear_settings(self) -> ApiResponse[CollectionStatusRead]:
        async with self._session_factory() as session:
            try:
                settings = await CollectionRepository(session).clear_current_room()
                await session.commit()
                return ApiResponse.ok(self._to_read(settings), "collection room cleared")
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection settings could not be cleared")

    async def run_once(self) -> ApiResponse[CollectionStatusRead]:
        if self._lock.locked():
            return await self.get_status(already_running=True)
        async with self._lock:
            return await self._run_locked()

    async def _run_locked(self) -> ApiResponse[CollectionStatusRead]:
        attempted_at = local_now()
        async with self._session_factory() as session:
            repository = CollectionRepository(session)
            try:
                settings = await repository.get_current_settings()
                if not self._has_room(settings):
                    await repository.update_current_status(status=CollectionStatus.NO_ROOM_CONFIGURED.value, message="no monitored room configured", attempted_at=attempted_at)
                    await session.commit()
                    return ApiResponse.ok(self._to_read(settings))
                room = self._room_values(settings)
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection settings could not be read")

        try:
            async with self._auth_manager.acquire_client() as client:
                async with self._session_factory() as session:
                    result = await self._monitoring_service.query_save_and_evaluate(session, client, **room)
        except SessionAccessError as exc:
            status = CollectionStatus.SESSION_EXPIRED if exc.code == ErrorCode.SESSION_EXPIRED else CollectionStatus.NOT_AUTHENTICATED
            return await self._record_terminal(status, exc.message, attempted_at)
        except Exception:
            # Scheduler calls must never let an unexpected provider/session failure escape.
            return await self._record_terminal(CollectionStatus.FAILED, "unexpected collection failure", attempted_at)

        if not result.success or result.data is None:
            status = CollectionStatus.SESSION_EXPIRED if result.code == ErrorCode.SESSION_EXPIRED else CollectionStatus.FAILED
            return await self._record_terminal(status, result.message, attempted_at)

        source_time = parse_source_time(result.data.reading.source_time)
        status = CollectionStatus.UPSTREAM_NOT_UPDATED if result.data.duplicate else CollectionStatus.SUCCESS
        message = "upstream source time already collected" if result.data.duplicate else "electricity snapshot collected"
        return await self._record_terminal(status, message, attempted_at, succeeded_at=local_now(), source_time=source_time)

    async def _record_terminal(
        self, status: CollectionStatus, message: str, attempted_at: datetime,
        *, succeeded_at: datetime | None = None, source_time: datetime | None = None,
    ) -> ApiResponse[CollectionStatusRead]:
        async with self._session_factory() as session:
            try:
                settings = await CollectionRepository(session).update_current_status(
                    status=status.value, message=message, attempted_at=attempted_at,
                    succeeded_at=succeeded_at, source_time=source_time,
                )
                await session.commit()
                return ApiResponse.ok(self._to_read(settings), message)
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection status could not be saved")

    def _to_read(self, settings: CollectionSettings, *, already_running: bool = False) -> CollectionStatusRead:
        return CollectionStatusRead(
            enabled=self._enabled and settings.enabled,
            scheduled_time=f"{self._hour:02d}:{self._minute:02d}",
            # TODO(Phase D): collection settings and scheduler need an explicit user scope.
            authenticated=getattr(self._auth_manager, "has_scheduler_client", lambda: self._auth_manager.get_client() is not None)(),
            area_id=settings.area_id, building_id=settings.building_id, building_name=settings.building_name,
            floor_id=settings.floor_id, floor_name=settings.floor_name, room_id=settings.room_id, room_name=settings.room_name,
            status=CollectionStatus.ALREADY_RUNNING if already_running else CollectionStatus(settings.status),
            message="collection is already running" if already_running else settings.message,
            last_attempt_time=settings.last_attempt_time, last_success_time=settings.last_success_time, last_source_time=settings.last_source_time,
        )

    @staticmethod
    def _has_room(settings: CollectionSettings) -> bool:
        return all((settings.area_id, settings.building_id, settings.floor_id, settings.room_id))

    @staticmethod
    def _room_values(settings: CollectionSettings) -> dict[str, str]:
        return {
            "area_id": settings.area_id or "", "building_id": settings.building_id or "",
            "floor_id": settings.floor_id or "", "room_id": settings.room_id or "",
            "room_name": settings.room_name or "",
        }
