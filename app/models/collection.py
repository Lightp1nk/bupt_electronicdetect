"""Single-user persisted configuration and status for automatic collection."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class CollectionSettings(Base):
    __tablename__ = "collection_settings"

    # This application is deliberately single-user: every read and write uses id=1.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    area_id: Mapped[str | None] = mapped_column(String(32))
    building_id: Mapped[str | None] = mapped_column(String(128))
    building_name: Mapped[str | None] = mapped_column(String(255))
    floor_id: Mapped[str | None] = mapped_column(String(128))
    floor_name: Mapped[str | None] = mapped_column(String(255))
    room_id: Mapped[str | None] = mapped_column(String(128))
    room_name: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="never_run")
    message: Mapped[str | None] = mapped_column(String(512))
    last_attempt_time: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_time: Mapped[datetime | None] = mapped_column(DateTime)
    last_source_time: Mapped[datetime | None] = mapped_column(DateTime)
