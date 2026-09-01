"""Historical electricity snapshot ORM model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class ElectricityRecord(Base):
    __tablename__ = "electricity_records"
    __table_args__ = (
        UniqueConstraint("area_id", "room_id", "source_time", name="uq_electricity_record_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    area_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    building_id: Mapped[str] = mapped_column(String(128), nullable=False)
    building_name: Mapped[str | None] = mapped_column(String(255))
    floor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    floor_name: Mapped[str | None] = mapped_column(String(255))
    room_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    room_name: Mapped[str | None] = mapped_column(String(255))
    remaining_money: Mapped[float | None] = mapped_column(Float)
    remaining_kwh: Mapped[float | None] = mapped_column(Float)
    remaining_energy_kwh: Mapped[float | None] = mapped_column(Float)
    free_remaining_kwh: Mapped[float | None] = mapped_column(Float)
    total_usage_kwh: Mapped[float | None] = mapped_column(Float)
    price_per_kwh: Mapped[float | None] = mapped_column(Float)
    source_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    query_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
