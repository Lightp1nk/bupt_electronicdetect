from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base
from app.models import alert, collection, electricity  # noqa: F401
from app.repositories.collection_repository import CollectionRepository
from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import CollectionSettingsUpdate, CollectionStatus, ElectricityReading
from app.services.auth_session import SessionAccessError
from app.services.collection_scheduler import JOB_ID, CollectionScheduleConfig, start_collection_scheduler
from app.services.collection_service import CollectionService
from app.services.monitoring_service import MonitoringService


async def service_at(path: Path, manager: object) -> tuple[object, CollectionService, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, CollectionService(sessions, manager, MonitoringService(asyncio.Lock()), enabled=True, hour=4, minute=0), sessions  # type: ignore[arg-type]


class FakeClient:
    def __init__(self, result: ApiResponse[ElectricityReading], *, wait: asyncio.Event | None = None) -> None:
        self.result, self.wait, self.calls = result, wait, 0

    async def query_electricity(self, **_: object) -> ApiResponse[ElectricityReading]:
        self.calls += 1
        if self.wait is not None:
            await self.wait.wait()
        return self.result


class FakeManager:
    def __init__(self, client: FakeClient | None = None, error: SessionAccessError | None = None) -> None:
        self.client, self.error = client, error

    def get_client(self) -> FakeClient | None:
        return self.client

    @asynccontextmanager
    async def acquire_client(self):
        if self.error is not None:
            raise self.error
        assert self.client is not None
        yield self.client


def reading() -> ElectricityReading:
    return ElectricityReading(
        area_id="2", building_id="b", floor_id="f", room_id="r", room_name="203",
        source_time="2026-09-01 04:01:00", remaining_kwh=98.2, total_usage_kwh=5204.73, raw_data={},
    )


async def configure(service: CollectionService) -> None:
    result = await service.save_settings(CollectionSettingsUpdate(
        area_id="2", building_id="b", building_name="B楼", floor_id="f", floor_name="2层", room_id="r", room_name="203",
    ))
    assert result.success


def test_no_room_configured_is_persisted(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, service, _ = await service_at(tmp_path / "no-room.db", FakeManager())
        result = await service.run_once()
        assert result.success and result.data.status == CollectionStatus.NO_ROOM_CONFIGURED
        assert result.data.last_attempt_time is not None
        await engine.dispose()

    asyncio.run(scenario())


def test_collection_states_and_duplicate_snapshot(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeClient(ApiResponse.ok(reading()))
        engine, service, sessions = await service_at(tmp_path / "success.db", FakeManager(client))
        await configure(service)
        first, second = await service.run_once(), await service.run_once()
        assert first.data.status == CollectionStatus.SUCCESS
        assert second.data.status == CollectionStatus.UPSTREAM_NOT_UPDATED
        assert client.calls == 2
        async with sessions() as session:
            assert len(await ElectricityRepository(session).get_history("2", "r")) == 1
        await engine.dispose()

    asyncio.run(scenario())


def test_not_authenticated_and_expired_never_call_provider(tmp_path: Path) -> None:
    async def scenario() -> None:
        not_logged_in = FakeManager(error=SessionAccessError(ErrorCode.AUTH_REQUIRED, "log in first"))
        engine, service, _ = await service_at(tmp_path / "auth.db", not_logged_in)
        await configure(service)
        result = await service.run_once()
        assert result.data.status == CollectionStatus.NOT_AUTHENTICATED
        expired = FakeManager(error=SessionAccessError(ErrorCode.SESSION_EXPIRED, "expired"))
        expired_engine, expired_service, _ = await service_at(tmp_path / "expired.db", expired)
        await configure(expired_service)
        expired_result = await expired_service.run_once()
        assert expired_result.data.status == CollectionStatus.SESSION_EXPIRED
        await engine.dispose()
        await expired_engine.dispose()

    asyncio.run(scenario())


def test_provider_error_is_recorded_without_escaping(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeClient(ApiResponse.error(ErrorCode.NETWORK_ERROR, "network unavailable"))
        engine, service, _ = await service_at(tmp_path / "failure.db", FakeManager(client))
        await configure(service)
        result = await service.run_once()
        assert result.success and result.data.status == CollectionStatus.FAILED
        assert result.data.message == "network unavailable"
        await engine.dispose()

    asyncio.run(scenario())


def test_manual_and_scheduler_calls_share_one_in_process_lock(tmp_path: Path) -> None:
    async def scenario() -> None:
        release = asyncio.Event()
        engine, service, _ = await service_at(tmp_path / "lock.db", FakeManager(FakeClient(ApiResponse.ok(reading()), wait=release)))
        await configure(service)
        running = asyncio.create_task(service.run_once())
        await asyncio.sleep(0)
        concurrent = await service.run_once()
        assert concurrent.data.status == CollectionStatus.ALREADY_RUNNING
        release.set()
        assert (await running).data.status == CollectionStatus.SUCCESS
        await engine.dispose()

    asyncio.run(scenario())


def test_async_scheduler_registers_one_beijing_time_job(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, service, _ = await service_at(tmp_path / "scheduler.db", FakeManager())
        scheduler = start_collection_scheduler(service, CollectionScheduleConfig(enabled=True, hour=4, minute=0))
        job = scheduler.get_job(JOB_ID)
        assert job is not None and job.max_instances == 1 and job.coalesce is True
        assert str(job.trigger.timezone) == "Asia/Shanghai"
        scheduler.shutdown(wait=False)
        await engine.dispose()

    asyncio.run(scenario())
