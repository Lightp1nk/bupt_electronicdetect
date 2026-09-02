"""Trigger one real notification from the isolated electricity test database."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.database.database import DATABASE_URL, SessionLocal
from app.models.electricity import ElectricityRecord
from app.models.user import User
from app.schemas.electricity import ElectricityReading
from app.services.alert_service import AlertService
from app.services.notification_providers import AstrBotBridgeNotifier
from app.services.notification_service import NotificationService


AREA_ID = "2"
ROOM_ID = "190815002099"


def _require_test_mode() -> None:
    if os.getenv("APP_DISABLE_UPSTREAM_QUERIES", "").lower() not in {"1", "true", "yes", "on"} or "test" not in DATABASE_URL:
        raise RuntimeError("refusing to trigger a test alert outside isolated test mode")


async def run() -> None:
    _require_test_mode()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).order_by(User.id))
        record = await session.scalar(
            select(ElectricityRecord)
            .where(ElectricityRecord.area_id == AREA_ID, ElectricityRecord.room_id == ROOM_ID)
            .order_by(ElectricityRecord.source_time.desc())
        )
        if user is None or record is None:
            raise RuntimeError("test user or simulated electricity record is missing")

        reading = ElectricityReading(
            area_id=record.area_id, building_id=record.building_id, building_name=record.building_name,
            floor_id=record.floor_id, floor_name=record.floor_name, room_id=record.room_id,
            room_name=record.room_name, source_time=record.source_time.isoformat(sep=" ") if record.source_time else None,
            remaining_money=record.remaining_money, remaining_kwh=record.remaining_kwh,
            remaining_energy_kwh=record.remaining_energy_kwh, total_usage_kwh=record.total_usage_kwh,
            free_remaining_kwh=record.free_remaining_kwh, price_per_kwh=record.price_per_kwh,
            raw_data=record.raw_data_json,
        )
        transitions = await AlertService(session).evaluate(user.id, reading)
        await NotificationService(session, AstrBotBridgeNotifier.from_environment()).process_transitions(transitions)
        print(f"TEST_ALERT_TRANSITIONS={len(transitions)}")
        print(f"TEST_ALERT_LEVEL={transitions[0].event.level if transitions else 'none'}")


if __name__ == "__main__":
    asyncio.run(run())
