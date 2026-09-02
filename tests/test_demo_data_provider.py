"""Demo data is presentation-only and must never mutate production tables."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.electricity import _read_provider
from app.data_providers.electricity import DemoElectricityDataProvider, RealElectricityDataProvider
from app.database.database import Base
from app.models import alert, electricity, notification_binding, notification_delivery  # noqa: F401
from app.models.alert import AlertEvent
from app.models.electricity import ElectricityRecord
from app.models.notification_delivery import NotificationDelivery
from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.electricity import ElectricityDataSource, ElectricityReading, PredictionMaturity
from app.services.electricity_service import ElectricityService
from app.services.statistics_service import StatisticsService


def test_demo_provider_has_continuous_history_and_drives_statistics() -> None:
    async def scenario() -> None:
        provider = DemoElectricityDataProvider()
        records = await provider.get_history("any-area", "any-room")
        assert len(records) >= 91
        assert all(
            (right.source_time.date() - left.source_time.date()).days == 1
            for left, right in zip(records, records[1:])
            if left.source_time is not None and right.source_time is not None
        )
        daily = [right.total_usage_kwh - left.total_usage_kwh for left, right in zip(records, records[1:])]
        assert max(daily) >= 15

        analysis = await StatisticsService(data_provider=provider).get_analysis(area_id="any-area", room_id="any-room")
        assert analysis.success and analysis.data is not None
        assert analysis.data.statistics.valid_daily_count >= 90
        assert analysis.data.statistics.avg_3d_kwh is not None
        assert analysis.data.statistics.avg_7d_kwh is not None
        assert analysis.data.prediction.maturity == PredictionMaturity.STABLE
        assert analysis.data.prediction.estimated_remaining_days is not None

    asyncio.run(scenario())


def test_demo_provider_never_writes_or_evaluates_alerts(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'real.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async with sessions() as session:
            before = [
                await session.scalar(select(func.count()).select_from(model))
                for model in (ElectricityRecord, AlertEvent, NotificationDelivery)
            ]
            provider = DemoElectricityDataProvider()
            await provider.get_latest("demo", "demo")
            result = await StatisticsService(data_provider=provider).get_analysis(area_id="demo", room_id="demo")
            assert result.success
            after = [
                await session.scalar(select(func.count()).select_from(model))
                for model in (ElectricityRecord, AlertEvent, NotificationDelivery)
            ]
            assert before == after == [0, 0, 0]
        await engine.dispose()

    asyncio.run(scenario())


def test_real_mode_keeps_using_electricity_records_and_demo_requires_explicit_enable(tmp_path: Path, monkeypatch) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'real.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sessions() as session:
            repository = ElectricityRepository(session)
            reading = ElectricityReading(area_id="real-area", building_id="b", floor_id="f", room_id="real-room", total_usage_kwh=12, raw_data={})
            await repository.add(reading, source_time=None, query_time=datetime(2026, 9, 2, 4, 0))
            await session.commit()

            real = await ElectricityService(session).get_history(area_id="real-area", room_id="real-room")
            assert real.success and len(real.data or []) == 1
            assert isinstance(_read_provider(session, ElectricityDataSource.REAL), RealElectricityDataProvider)
            monkeypatch.delenv("DEMO_MODE_ENABLED", raising=False)
            assert _read_provider(session, ElectricityDataSource.DEMO) is None
            monkeypatch.setenv("DEMO_MODE_ENABLED", "true")
            assert isinstance(_read_provider(session, ElectricityDataSource.DEMO), DemoElectricityDataProvider)
        await engine.dispose()

    asyncio.run(scenario())


def test_legacy_frontend_mock_is_removed() -> None:
    assert not Path("frontend/src/mock/dashboard.ts").exists()
