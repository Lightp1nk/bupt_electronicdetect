from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.services.electricity_service as service_module
from app.database.database import Base
from app.models import electricity  # noqa: F401
from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import ElectricityReading
from app.services.electricity_service import ElectricityService


class FakeBUPTClient:
    def __init__(self, result: ApiResponse[ElectricityReading]) -> None:
        self.result = result
        self.calls = 0

    async def query_electricity(self, **_: object) -> ApiResponse[ElectricityReading]:
        self.calls += 1
        return self.result


def reading(source_time: str | None = "2026-09-01 15:00:00.0") -> ElectricityReading:
    return ElectricityReading(
        area_id="2", building_id="b", building_name="B楼", floor_id="f", floor_name="2层",
        room_id="r", room_name="203", source_time=source_time, remaining_money=47.14,
        remaining_kwh=98.2, total_usage_kwh=5204.73, price_per_kwh=0.48, raw_data={"price": "0.48"},
    )


async def service_at(path: Path) -> tuple[object, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_query_save_deduplicate_and_history(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, sessions = await service_at(tmp_path / "service.db")
        client = FakeBUPTClient(ApiResponse.ok(reading()))
        async with sessions() as session:
            service = ElectricityService(session)
            first = await service.query_and_save(client, area_id="2", building_id="b", floor_id="f", room_id="r", room_name="203")
            duplicate = await service.query_and_save(client, area_id="2", building_id="b", floor_id="f", room_id="r", room_name="203")
            assert first.success and first.data.saved and not first.data.duplicate
            assert duplicate.success and not duplicate.data.saved and duplicate.data.duplicate
            history = await service.get_history(area_id="2", room_id="r")
            assert len(history.data) == 1
        await engine.dispose()

    asyncio.run(scenario())


def test_new_source_time_and_days_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "local_now", lambda: datetime(2026, 9, 10, 12, 0))

    async def scenario() -> None:
        engine, sessions = await service_at(tmp_path / "times.db")
        async with sessions() as session:
            service = ElectricityService(session)
            await service.query_and_save(FakeBUPTClient(ApiResponse.ok(reading("2026-01-01 10:00:00"))), area_id="2", building_id="b", floor_id="f", room_id="r")
            await service.query_and_save(FakeBUPTClient(ApiResponse.ok(reading("2026-09-01 10:00:00"))), area_id="2", building_id="b", floor_id="f", room_id="r")
            all_records = await service.get_history(area_id="2", room_id="r")
            recent = await service.get_history(area_id="2", room_id="r", days=30)
            latest = await service.get_latest(area_id="2", room_id="r")
            assert len(all_records.data) == 2
            assert len(recent.data) == 1
            assert latest.data.source_time == datetime(2026, 9, 1, 10, 0)
        await engine.dispose()

    asyncio.run(scenario())


def test_provider_failure_does_not_write(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, sessions = await service_at(tmp_path / "provider-failure.db")
        async with sessions() as session:
            service = ElectricityService(session)
            failed = await service.query_and_save(
                FakeBUPTClient(ApiResponse.error(ErrorCode.SESSION_EXPIRED, "expired")),
                area_id="2", building_id="b", floor_id="f", room_id="r",
            )
            history = await service.get_history(area_id="2", room_id="r")
            assert failed.code == ErrorCode.SESSION_EXPIRED
            assert history.data == []
        await engine.dispose()

    asyncio.run(scenario())


def test_database_error_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_add(self: ElectricityRepository, *_: object, **__: object) -> object:
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(service_module.ElectricityRepository, "add", failing_add)

    async def scenario() -> None:
        engine, sessions = await service_at(tmp_path / "db-failure.db")
        async with sessions() as session:
            result = await ElectricityService(session).query_and_save(
                FakeBUPTClient(ApiResponse.ok(reading())), area_id="2", building_id="b", floor_id="f", room_id="r"
            )
            assert result.code == ErrorCode.DATABASE_ERROR
        await engine.dispose()

    asyncio.run(scenario())
