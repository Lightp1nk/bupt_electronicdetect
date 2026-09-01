"""User-scoped manual collection; scheduled multi-user collection is deferred to Phase D."""

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
from app.services.electricity_service import local_now, parse_source_time
from app.services.monitoring_service import MonitoringService


class CollectionService:
    """Operate on one user's monitored room without creating an implicit singleton."""

    def __init__(
        self, session_factory: Callable[[], AsyncSession], auth_manager: AuthSessionManager, monitoring_service: MonitoringService,
        *, enabled: bool, hour: int, minute: int,
    ) -> None:
        self._session_factory = session_factory
        self._auth_manager = auth_manager
        self._monitoring_service = monitoring_service
        self._enabled, self._hour, self._minute = enabled, hour, minute
        self._locks: dict[int, asyncio.Lock] = {}

    async def get_status(self, user_id: int, *, already_running: bool = False) -> ApiResponse[CollectionStatusRead]:
        async with self._session_factory() as session:
            try:
                settings = await CollectionRepository(session).get_settings(user_id)
                return ApiResponse.ok(self._to_read(settings, user_id=user_id, already_running=already_running))
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection status could not be read")

    async def save_settings(self, user_id: int, payload: CollectionSettingsUpdate) -> ApiResponse[CollectionStatusRead]:
        async with self._session_factory() as session:
            try:
                settings = await CollectionRepository(session).update_settings(user_id, **payload.model_dump())
                await session.commit()
                return ApiResponse.ok(self._to_read(settings, user_id=user_id), "collection settings saved")
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection settings could not be saved")

    async def clear_settings(self, user_id: int) -> ApiResponse[CollectionStatusRead]:
        async with self._session_factory() as session:
            try:
                await CollectionRepository(session).clear_settings(user_id)
                await session.commit()
                return ApiResponse.ok(self._to_read(None, user_id=user_id), "collection room cleared")
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection settings could not be cleared")

    async def run_once(self, user_id: int) -> ApiResponse[CollectionStatusRead]:
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        if lock.locked():
            return await self.get_status(user_id, already_running=True)
        async with lock:
            return await self._run_locked(user_id)

    async def _run_locked(self, user_id: int) -> ApiResponse[CollectionStatusRead]:
        attempted_at = local_now()
        async with self._session_factory() as session:
            try:
                settings = await CollectionRepository(session).get_settings(user_id)
                if not self._has_room(settings):
                    return ApiResponse.ok(self._to_read(settings, user_id=user_id, status=CollectionStatus.NO_ROOM_CONFIGURED))
                room = self._room_values(settings)
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection settings could not be read")

        try:
            async with self._auth_manager.acquire_client(user_id) as client:
                async with self._session_factory() as session:
                    result = await self._monitoring_service.query_save_and_evaluate(user_id, session, client, **room)
        except SessionAccessError as exc:
            status = CollectionStatus.SESSION_EXPIRED if exc.code == ErrorCode.SESSION_EXPIRED else CollectionStatus.NOT_AUTHENTICATED
            return await self._record_terminal(user_id, status, exc.message, attempted_at)
        except Exception:
            return await self._record_terminal(user_id, CollectionStatus.FAILED, "unexpected collection failure", attempted_at)

        if not result.success or result.data is None:
            status = CollectionStatus.SESSION_EXPIRED if result.code == ErrorCode.SESSION_EXPIRED else CollectionStatus.FAILED
            return await self._record_terminal(user_id, status, result.message, attempted_at)

        source_time = parse_source_time(result.data.reading.source_time)
        status = CollectionStatus.UPSTREAM_NOT_UPDATED if result.data.duplicate else CollectionStatus.SUCCESS
        message = "upstream source time already collected" if result.data.duplicate else "electricity snapshot collected"
        return await self._record_terminal(user_id, status, message, attempted_at, succeeded_at=local_now(), source_time=source_time)

    async def _record_terminal(
        self, user_id: int, status: CollectionStatus, message: str, attempted_at: datetime,
        *, succeeded_at: datetime | None = None, source_time: datetime | None = None,
    ) -> ApiResponse[CollectionStatusRead]:
        async with self._session_factory() as session:
            try:
                settings = await CollectionRepository(session).update_status(
                    user_id, status=status.value, message=message, attempted_at=attempted_at,
                    succeeded_at=succeeded_at, source_time=source_time,
                )
                await session.commit()
                return ApiResponse.ok(self._to_read(settings, user_id=user_id, status=status), message)
            except SQLAlchemyError:
                await session.rollback()
                return ApiResponse.error(ErrorCode.DATABASE_ERROR, "collection status could not be saved")

    def _to_read(
        self, settings: CollectionSettings | None, *, user_id: int, already_running: bool = False,
        status: CollectionStatus | None = None,
    ) -> CollectionStatusRead:
        current_status = status or (CollectionStatus(settings.status) if settings is not None else CollectionStatus.NEVER_RUN)
        if already_running:
            current_status = CollectionStatus.ALREADY_RUNNING
        return CollectionStatusRead(
            enabled=self._enabled and (settings.enabled if settings is not None else False),
            scheduled_time=f"{self._hour:02d}:{self._minute:02d}",
            authenticated=self._auth_manager.has_client(user_id),
            area_id=settings.area_id if settings else None, area_name=settings.area_name if settings else None,
            building_id=settings.building_id if settings else None, building_name=settings.building_name if settings else None,
            floor_id=settings.floor_id if settings else None, floor_name=settings.floor_name if settings else None,
            room_id=settings.room_id if settings else None, room_name=settings.room_name if settings else None,
            status=current_status,
            message="collection is already running" if already_running else (settings.message if settings else None),
            last_attempt_time=settings.last_attempt_time if settings else None,
            last_success_time=settings.last_success_time if settings else None,
            last_source_time=settings.last_source_time if settings else None,
        )

    @staticmethod
    def _has_room(settings: CollectionSettings | None) -> bool:
        return settings is not None and all((settings.area_id, settings.building_id, settings.floor_id, settings.room_id))

    @staticmethod
    def _room_values(settings: CollectionSettings) -> dict[str, str]:
        return {
            "area_id": settings.area_id or "", "building_id": settings.building_id or "",
            "floor_id": settings.floor_id or "", "room_id": settings.room_id or "",
            "room_name": settings.room_name or "",
        }
