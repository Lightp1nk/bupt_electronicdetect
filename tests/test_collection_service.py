from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base
from app.models import alert, collection, electricity, upstream_session, user  # noqa: F401
from app.repositories.collection_repository import CollectionRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import CollectionSettingsUpdate, CollectionStatus, ElectricityReading
from app.services.auth_session import SessionAccessError
from app.services.collection_scheduler import JOB_ID, CollectionScheduleConfig, start_collection_scheduler
from app.services.collection_service import CollectionService
from app.services.monitoring_service import MonitoringService


class FakeClient:
    def __init__(self, result: ApiResponse[ElectricityReading], wait: asyncio.Event | None = None) -> None:
        self.result, self.wait, self.calls = result, wait, 0

    async def query_electricity(self, **_: object) -> ApiResponse[ElectricityReading]:
        self.calls += 1
        if self.wait is not None:
            await self.wait.wait()
        return self.result


class FakeManager:
    def __init__(self, client: FakeClient | None = None, error: SessionAccessError | None = None) -> None:
        self.client, self.error, self.requested_users = client, error, []

    def has_client(self, user_id: int) -> bool:
        return self.client is not None

    @asynccontextmanager
    async def acquire_client(self, user_id: int):
        self.requested_users.append(user_id)
        if self.error is not None:
            raise self.error
        assert self.client is not None
        yield self.client


async def service_at(path: Path, manager: FakeManager) -> tuple[object, CollectionService, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, CollectionService(sessions, manager, MonitoringService(), enabled=True, hour=4, minute=0), sessions


def reading(room_id: str = "r") -> ElectricityReading:
    return ElectricityReading(area_id="2", building_id="b", floor_id="f", room_id=room_id, room_name="203", source_time="2026-09-01 04:01:00", remaining_kwh=98.2, total_usage_kwh=5204.73, raw_data={})


def payload(room_id: str) -> CollectionSettingsUpdate:
    return CollectionSettingsUpdate(area_id="2", area_name="沙河", building_id="b", building_name="B楼", floor_id="f", floor_name="2层", room_id=room_id, room_name=f"{room_id}室")


def test_user_settings_are_isolated_and_clear_does_not_affect_other_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, service, sessions = await service_at(tmp_path / "settings.db", FakeManager())
        assert (await service.get_status(1)).data.room_id is None
        await service.save_settings(1, payload("a"))
        await service.save_settings(2, payload("b"))
        assert (await service.get_status(1)).data.room_id == "a"
        assert (await service.get_status(2)).data.room_id == "b"
        await service.save_settings(1, payload("a-new"))
        await service.clear_settings(1)
        assert (await service.get_status(1)).data.room_id is None
        assert (await service.get_status(2)).data.room_id == "b"
        async with sessions() as session:
            assert await CollectionRepository(session).get_settings(1) is None
            assert (await CollectionRepository(session).get_settings(2)).room_id == "b"
        await engine.dispose()

    asyncio.run(scenario())


def test_manual_collection_uses_current_user_room_and_runtime_client(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = FakeManager(FakeClient(ApiResponse.ok(reading("a"))))
        engine, service, _ = await service_at(tmp_path / "run.db", manager)
        missing = await service.run_once(1)
        assert missing.data.status == CollectionStatus.NO_ROOM_CONFIGURED
        await service.save_settings(2, payload("a"))
        first, duplicate = await service.run_once(2), await service.run_once(2)
        assert first.data.status == CollectionStatus.SUCCESS
        assert duplicate.data.status == CollectionStatus.UPSTREAM_NOT_UPDATED
        assert manager.requested_users == [2, 2]
        await engine.dispose()

    asyncio.run(scenario())


def test_collection_session_failure_is_recorded_for_only_requested_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, service, _ = await service_at(tmp_path / "auth.db", FakeManager(error=SessionAccessError(ErrorCode.SESSION_EXPIRED, "expired")))
        await service.save_settings(1, payload("a"))
        result = await service.run_once(1)
        assert result.data.status == CollectionStatus.SESSION_EXPIRED
        await engine.dispose()

    asyncio.run(scenario())


def test_same_user_collection_runs_are_serialized(tmp_path: Path) -> None:
    async def scenario() -> None:
        release = asyncio.Event()
        manager = FakeManager(FakeClient(ApiResponse.ok(reading("a")), release))
        engine, service, _ = await service_at(tmp_path / "lock.db", manager)
        await service.save_settings(1, payload("a"))
        running = asyncio.create_task(service.run_once(1))
        await asyncio.sleep(0)
        assert (await service.run_once(1)).data.status == CollectionStatus.ALREADY_RUNNING
        release.set()
        assert (await running).data.status == CollectionStatus.SUCCESS
        await engine.dispose()

    asyncio.run(scenario())


def test_scheduler_is_paused_until_phase_d_multi_user_scope(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, service, _ = await service_at(tmp_path / "scheduler.db", FakeManager())
        scheduler = start_collection_scheduler(service, CollectionScheduleConfig(enabled=True, hour=4, minute=0))
        assert scheduler.get_job(JOB_ID) is None
        scheduler.shutdown(wait=False)
        await engine.dispose()

    asyncio.run(scenario())
