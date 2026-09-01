from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base
from app.models import electricity  # noqa: F401
from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.electricity import ElectricityReading


def reading(*, room_id: str = "room-1") -> ElectricityReading:
    return ElectricityReading(
        area_id="2",
        building_id="building-1",
        building_name="B楼",
        floor_id="floor-2",
        floor_name="2层",
        room_id=room_id,
        room_name="203",
        remaining_money=47.14,
        remaining_kwh=98.2,
        total_usage_kwh=5204.73,
        price_per_kwh=0.48,
        raw_data={"surplus": "47.14"},
    )


async def database_at(path: Path) -> tuple[object, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_insert_read_optional_and_raw_data(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, sessions = await database_at(tmp_path / "records.db")
        moment = datetime(2026, 9, 1, 15, 0)
        async with sessions() as session:
            record = await ElectricityRepository(session).add(reading(), source_time=moment, query_time=moment)
            await session.commit()
            assert record.id is not None
        async with sessions() as session:
            latest = await ElectricityRepository(session).get_latest("2", "room-1")
            assert latest is not None
            assert latest.remaining_energy_kwh is None
            assert latest.raw_data_json == {"surplus": "47.14"}
        await engine.dispose()

    asyncio.run(scenario())


def test_history_order_limit_and_room_isolation(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, sessions = await database_at(tmp_path / "history.db")
        first = datetime(2026, 9, 1, 10, 0)
        second = first + timedelta(hours=1)
        async with sessions() as session:
            repo = ElectricityRepository(session)
            await repo.add(reading(), source_time=second, query_time=second)
            await repo.add(reading(), source_time=first, query_time=first)
            await repo.add(reading(room_id="room-2"), source_time=first, query_time=first)
            await session.commit()
            history = await repo.get_history("2", "room-1")
            limited = await repo.get_history("2", "room-1", limit=1)
            latest = await repo.get_latest("2", "room-1")
            assert [record.source_time for record in history] == [first, second]
            assert [record.source_time for record in limited] == [second]
            assert latest.source_time == second
        await engine.dispose()

    asyncio.run(scenario())


def test_missing_source_time_is_not_deduplicated_by_constraint(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, sessions = await database_at(tmp_path / "null-source.db")
        moment = datetime(2026, 9, 1, 12, 0)
        async with sessions() as session:
            repo = ElectricityRepository(session)
            await repo.add(reading(), source_time=None, query_time=moment)
            await repo.add(reading(), source_time=None, query_time=moment + timedelta(seconds=1))
            await session.commit()
            assert len(await repo.get_history("2", "room-1")) == 2
        await engine.dispose()

    asyncio.run(scenario())
