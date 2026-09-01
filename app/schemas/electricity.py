"""Normalized electricity reading while retaining every upstream field."""

from typing import Any

from pydantic import BaseModel, Field


class ElectricityReading(BaseModel):
    area_id: str
    building_id: str
    building_name: str | None = None
    floor_id: str
    floor_name: str | None = None
    room_id: str
    room_name: str | None = None
    source_time: str | None = None
    remaining_money: float | None = None
    remaining_kwh: float | None = None
    remaining_energy_kwh: float | None = None
    total_usage_kwh: float | None = None
    free_remaining_kwh: float | None = None
    price_per_kwh: float | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)
