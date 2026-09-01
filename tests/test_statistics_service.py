from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base
from app.models import electricity  # noqa: F401
from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.electricity import ElectricityReading
from app.schemas.electricity import PredictionMaturity
from app.services.statistics_service import StatisticsService, UsageSnapshot


BASE = datetime(2026, 9, 1, 3, 0)


def snapshots(*totals: float | None) -> list[UsageSnapshot]:
    return [UsageSnapshot(BASE + timedelta(days=index), total, index) for index, total in enumerate(totals)]


def usages(result: object) -> list[float]:
    return [item.usage_kwh for item in result.daily_usage]  # type: ignore[attr-defined]


def test_two_consecutive_source_dates_produce_one_daily_usage() -> None:
    result = StatisticsService.calculate(snapshots(100, 105))
    assert usages(result) == [5]
    assert result.valid_daily_count == 1


def test_three_consecutive_source_dates_produce_each_difference() -> None:
    result = StatisticsService.calculate(snapshots(100, 105, 109))
    assert usages(result) == [5, 4]


def test_missing_source_date_does_not_create_or_fill_daily_usage() -> None:
    result = StatisticsService.calculate([
        UsageSnapshot(BASE, 100),
        UsageSnapshot(BASE + timedelta(days=2), 110),
    ])
    assert result.daily_usage == ()


def test_decreasing_total_usage_is_anomaly_not_negative_daily_usage() -> None:
    result = StatisticsService.calculate(snapshots(100, 90))
    assert result.daily_usage == ()


def test_same_source_date_uses_latest_valid_snapshot_deterministically() -> None:
    result = StatisticsService.calculate([
        UsageSnapshot(BASE + timedelta(hours=20), 102, 2),
        UsageSnapshot(BASE, 100, 1),
        UsageSnapshot(BASE + timedelta(days=1), 107, 3),
    ])
    assert usages(result) == [5]


def test_same_timestamp_uses_sequence_as_deterministic_tie_breaker() -> None:
    result = StatisticsService.calculate([
        UsageSnapshot(BASE, 100, 1),
        UsageSnapshot(BASE, 102, 2),
        UsageSnapshot(BASE + timedelta(days=1), 107, 3),
    ])
    assert usages(result) == [5]


def test_null_total_usage_does_not_participate() -> None:
    result = StatisticsService.calculate(snapshots(100, None, 109))
    assert result.daily_usage == ()


def test_zero_usage_is_valid_but_does_not_divide_in_prediction_selection() -> None:
    result = StatisticsService.calculate(snapshots(100, 100, 100, 100))
    assert usages(result) == [0, 0, 0]
    assert result.avg_3d_kwh == 0
    assert result.maturity == PredictionMaturity.PRELIMINARY
    assert result.selected_average == (0, 3)


def test_fewer_than_three_daily_points_is_insufficient() -> None:
    result = StatisticsService.calculate(snapshots(100, 102, 105))
    assert result.maturity == PredictionMaturity.INSUFFICIENT
    assert result.avg_3d_kwh is None
    assert result.selected_average == (None, None)


def test_three_daily_points_use_three_day_average_and_preliminary_maturity() -> None:
    result = StatisticsService.calculate(snapshots(100, 102, 106, 112))
    assert result.avg_3d_kwh == 4
    assert result.avg_7d_kwh is None
    assert result.maturity == PredictionMaturity.PRELIMINARY
    assert result.selected_average == (4, 3)


def test_seven_daily_points_use_seven_day_average_and_stable_maturity() -> None:
    result = StatisticsService.calculate(snapshots(100, 101, 103, 106, 110, 115, 121, 128))
    assert result.avg_3d_kwh == 6
    assert result.avg_7d_kwh == 4
    assert result.maturity == PredictionMaturity.STABLE
    assert result.selected_average == (4, 7)


def test_zero_average_keeps_prediction_null_without_division_by_zero(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'statistics.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sessions() as session:
            repository = ElectricityRepository(session)
            for index in range(4):
                moment = BASE + timedelta(days=index)
                await repository.add(ElectricityReading(
                    area_id='2', building_id='b', floor_id='f', room_id='r',
                    remaining_kwh=10, total_usage_kwh=100, raw_data={},
                ), source_time=moment, query_time=moment)
            await session.commit()
            result = await StatisticsService(session).get_analysis(area_id='2', room_id='r')
            assert result.success and result.data is not None
            assert result.data.prediction.average_daily_usage_kwh == 0
            assert result.data.prediction.estimated_remaining_days is None
        await engine.dispose()

    asyncio.run(scenario())
