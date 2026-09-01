from __future__ import annotations
import asyncio
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.database.database import Base
from app.models import alert, collection, electricity  # noqa: F401
from app.schemas.electricity import AlertEventStatus, AlertLevel, AlertType, ElectricityReading
from app.services.alert_service import AlertService

def reading(money: float | None) -> ElectricityReading:
    return ElectricityReading(area_id="2", building_id="b", building_name="B楼", floor_id="f", floor_name="2层", room_id="r", room_name="203", remaining_money=money, source_time="2026-09-01 04:00:00", raw_data={})

def test_balance_alert_episode_lifecycle_and_unknown_value(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'alerts.db').as_posix()}")
        async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sessions() as s:
            service = AlertService(s)
            await service.evaluate(reading(25)); assert (await service.list_events("2", "r", None, 10)).data == []
            await service.evaluate(reading(18)); events = (await service.list_events("2", "r", None, 10)).data; assert len(events) == 1 and events[0].level == AlertLevel.WARNING
            first_id = events[0].id
            await service.evaluate(reading(17)); assert len((await service.list_events("2", "r", None, 10)).data) == 1
            await service.evaluate(reading(8)); event = (await service.list_events("2", "r", AlertEventStatus.ACTIVE, 10)).data[0]; assert event.id == first_id and event.level == AlertLevel.CRITICAL
            await service.evaluate(reading(15)); assert (await service.list_events("2", "r", AlertEventStatus.ACTIVE, 10)).data[0].level == AlertLevel.WARNING
            await service.evaluate(reading(None)); assert len((await service.list_events("2", "r", AlertEventStatus.ACTIVE, 10)).data) == 1
            await service.evaluate(reading(35)); assert (await service.list_events("2", "r", AlertEventStatus.ACTIVE, 10)).data == []
            await service.evaluate(reading(18)); events = (await service.list_events("2", "r", None, 10)).data; assert len(events) == 2 and events[0].status == AlertEventStatus.ACTIVE
        await engine.dispose()
    asyncio.run(scenario())

def test_remaining_days_lifecycle_unknown_prediction_and_disabled_settings(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'days.db').as_posix()}")
        async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sessions() as s:
            service = AlertService(s); settings = await service._repo.get_current_settings(); base = reading(50)
            # Prediction-unavailable/insufficient input is unknown and cannot create an event.
            await service.evaluate(ElectricityReading.model_validate({**base.model_dump(), 'remaining_kwh': 10}))
            assert (await service.list_events('2','r',None,10)).data == []
            await service._evaluate_value(base, settings, AlertType.LOW_REMAINING_DAYS, 6, True, 7, 3)
            await s.commit(); event = (await service.list_events('2','r',AlertEventStatus.ACTIVE,10)).data[0]; assert event.level == AlertLevel.WARNING
            await service._evaluate_value(base, settings, AlertType.LOW_REMAINING_DAYS, 2, True, 7, 3)
            await s.commit(); assert (await service.list_events('2','r',AlertEventStatus.ACTIVE,10)).data[0].level == AlertLevel.CRITICAL
            await service._evaluate_value(base, settings, AlertType.LOW_REMAINING_DAYS, None, True, 7, 3)
            await s.commit(); assert len((await service.list_events('2','r',AlertEventStatus.ACTIVE,10)).data) == 1
            await service._evaluate_value(base, settings, AlertType.LOW_REMAINING_DAYS, 8, True, 7, 3)
            await s.commit(); assert (await service.list_events('2','r',AlertEventStatus.ACTIVE,10)).data == []
            settings.enabled = False; await service._evaluate_value(reading(8), settings, AlertType.LOW_BALANCE, 8, False, 20, 10); await s.commit()
            assert len((await service.list_events('2','r',None,10)).data) == 1
        await engine.dispose()
    asyncio.run(scenario())
