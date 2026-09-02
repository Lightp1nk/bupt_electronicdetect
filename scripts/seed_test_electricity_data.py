"""Seed a realistic, deterministic one-year electricity history for the isolated test database."""

from __future__ import annotations

import asyncio
import math
import os
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.database.database import DATABASE_URL, SessionLocal
from app.models.electricity import ElectricityRecord


AREA_ID = "2"
BUILDING_ID = "190815002"
FLOOR_ID = "4"
ROOM_ID = "190815002099"
FINAL_TOTAL_USAGE_KWH = 8030.0
FINAL_REMAINING_MONEY = 9.0
FINAL_REMAINING_KWH = 18.0
DAY_COUNT = 366


def _require_test_mode() -> None:
    disabled = os.getenv("APP_DISABLE_UPSTREAM_QUERIES", "").lower() in {"1", "true", "yes", "on"}
    if not disabled or "test" not in DATABASE_URL.lower():
        raise RuntimeError("refusing to seed data outside isolated test mode")


def _daily_usage(index: int) -> float:
    """A reproducible mix of weekly rhythm, short cycles, and a mild seasonal change."""
    weekly = 0.42 * math.sin((index + 1) * 2 * math.pi / 7)
    short_cycle = 0.55 * math.sin(index * 0.47) + 0.26 * math.cos(index * 0.19)
    seasonal = 0.34 * math.sin((index - 45) * 2 * math.pi / 365)
    weekend_adjustment = -0.38 if index % 7 in {5, 6} else 0.16
    return round(max(3.7, min(7.8, 5.85 + weekly + short_cycle + seasonal + weekend_adjustment)), 2)


async def run() -> None:
    _require_test_mode()
    end_time = datetime.now().replace(hour=3, minute=4, second=0, microsecond=0)
    usages = [_daily_usage(index) for index in range(DAY_COUNT - 1)]
    starting_total = round(FINAL_TOTAL_USAGE_KWH - sum(usages), 2)
    source_times = [end_time - timedelta(days=DAY_COUNT - 1 - index) for index in range(DAY_COUNT)]

    total_usage = starting_total
    async with SessionLocal() as session:
        await session.execute(delete(ElectricityRecord).where(ElectricityRecord.area_id == AREA_ID, ElectricityRecord.room_id == ROOM_ID))
        for index, source_time in enumerate(source_times):
            if index:
                total_usage = round(total_usage + usages[index - 1], 2)
            consumed = total_usage - starting_total
            money = round(FINAL_REMAINING_MONEY + (sum(usages) - consumed) * 0.0194, 2)
            remaining_kwh = round(FINAL_REMAINING_KWH + (sum(usages) - consumed) * 0.52, 2)
            session.add(ElectricityRecord(
                area_id=AREA_ID,
                building_id=BUILDING_ID,
                building_name="雁北园A楼",
                floor_id=FLOOR_ID,
                floor_name="4层",
                room_id=ROOM_ID,
                room_name="A楼419",
                remaining_money=money,
                remaining_kwh=remaining_kwh,
                remaining_energy_kwh=remaining_kwh,
                free_remaining_kwh=None,
                total_usage_kwh=total_usage,
                price_per_kwh=0.0194,
                source_time=source_time,
                query_time=source_time,
                created_at=source_time,
                raw_data_json={"source": "isolated_test_simulation", "day_index": index},
            ))
        await session.commit()
    print(f"TEST_HISTORY_DAYS={DAY_COUNT}")
    print(f"TEST_FINAL_BALANCE={FINAL_REMAINING_MONEY:.2f}")
    print(f"TEST_FINAL_TOTAL_USAGE={FINAL_TOTAL_USAGE_KWH:.2f}")


if __name__ == "__main__":
    asyncio.run(run())
