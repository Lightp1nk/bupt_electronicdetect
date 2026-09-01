"""Single-user alert settings and durable alert-event lifecycle records."""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base

class AlertSettings(Base):
    __tablename__ = "alert_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    low_balance_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    balance_warning_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=20.0)
    balance_critical_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)
    low_remaining_days_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remaining_days_warning_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=7.0)
    remaining_days_critical_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)

class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    area_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    building_name: Mapped[str | None] = mapped_column(String(255))
    floor_name: Mapped[str | None] = mapped_column(String(255))
    room_name: Mapped[str | None] = mapped_column(String(255))
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    trigger_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    source_time: Mapped[datetime | None] = mapped_column(DateTime)
    first_triggered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
