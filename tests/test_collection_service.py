from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base
from app.models import alert, collection, electricity, upstream_session, user  # noqa: F401
from app.models.collection import CollectionSettings
from app.models.user import User
from app.repositories.collection_repository import CollectionRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import CollectionSettingsUpdate, CollectionStatus, ElectricityReading
from app.services.auth_session import SessionAccessError
from app.services.collection_scheduler import JOB_ID, CollectionScheduleConfig, MultiUserCollectionScheduler, start_collection_scheduler
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


def test_multi_user_scheduler_isolates_failures_skips_disabled_and_limits_concurrency(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'scheduler.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        from app.services.electricity_service import local_now
        now = local_now()
        async with sessions() as session:
            session.add_all([
                User(id=1, bupt_username="one", created_at=now, last_login_at=now),
                User(id=2, bupt_username="two", created_at=now, last_login_at=now),
                User(id=3, bupt_username="three", created_at=now, last_login_at=now),
            ])
            session.add_all([
                CollectionSettings(user_id=1, area_id="2", building_id="b", floor_id="f", room_id="a", enabled=True),
                CollectionSettings(user_id=2, area_id="2", building_id="b", floor_id="f", room_id="b", enabled=True),
                CollectionSettings(user_id=3, area_id="2", building_id="b", floor_id="f", room_id="c", enabled=False),
                # This orphan must never be scheduled, even if SQLite foreign keys are disabled.
                CollectionSettings(user_id=99, area_id="2", building_id="b", floor_id="f", room_id="orphan", enabled=True),
            ])
            await session.commit()

        class RecordingService:
            def __init__(self) -> None:
                self.users: list[int] = []
                self.running = 0
                self.maximum = 0

            async def run_once(self, user_id: int) -> None:
                self.users.append(user_id)
                self.running += 1
                self.maximum = max(self.maximum, self.running)
                await asyncio.sleep(0.02)
                self.running -= 1
                if user_id == 2:
                    raise RuntimeError("isolated failure")

        service = RecordingService()
        multi = MultiUserCollectionScheduler(sessions, service, max_concurrency=1)  # type: ignore[arg-type]
        await multi.run_all_once()
        assert service.users == [1, 2]
        assert service.maximum == 1

        scheduler = start_collection_scheduler(multi, CollectionScheduleConfig(enabled=True, hour=4, minute=0, max_concurrency=3))
        job = scheduler.get_job(JOB_ID)
        assert job is not None and job.max_instances == 1 and job.coalesce is True
        scheduler.shutdown(wait=False)
        await engine.dispose()

    asyncio.run(scenario())


def test_multi_user_scheduler_honors_configured_parallelism(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'parallel.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        from app.services.electricity_service import local_now
        now = local_now()
        async with sessions() as session:
            for user_id in range(1, 5):
                session.add(User(id=user_id, bupt_username=f"u{user_id}", created_at=now, last_login_at=now))
                session.add(CollectionSettings(user_id=user_id, area_id="2", building_id="b", floor_id="f", room_id=str(user_id), enabled=True))
            await session.commit()

        class ParallelService:
            def __init__(self) -> None: self.running = 0; self.maximum = 0; self.users: list[int] = []
            async def run_once(self, user_id: int) -> None:
                self.users.append(user_id); self.running += 1; self.maximum = max(self.maximum, self.running)
                await asyncio.sleep(0.02); self.running -= 1

        service = ParallelService()
        await MultiUserCollectionScheduler(sessions, service, max_concurrency=2).run_all_once()  # type: ignore[arg-type]
        assert sorted(service.users) == [1, 2, 3, 4]
        assert service.maximum == 2
        await engine.dispose()
    asyncio.run(scenario())
