"""APScheduler lifecycle helpers for this single-process FastAPI application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.services.collection_service import CollectionService


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
JOB_ID = "daily-electricity-collection"


@dataclass(frozen=True)
class CollectionScheduleConfig:
    enabled: bool = True
    hour: int = 4
    minute: int = 0

    @classmethod
    def from_environment(cls) -> "CollectionScheduleConfig":
        enabled = os.getenv("ELECTRICITY_COLLECTION_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
        hour, minute = int(os.getenv("ELECTRICITY_COLLECTION_HOUR", "4")), int(os.getenv("ELECTRICITY_COLLECTION_MINUTE", "0"))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("collection hour/minute must form a valid local time")
        return cls(enabled=enabled, hour=hour, minute=minute)


def start_collection_scheduler(service: CollectionService, config: CollectionScheduleConfig) -> AsyncIOScheduler:
    """Start the scheduler without a collection job until Phase D adds user scope."""
    scheduler = AsyncIOScheduler(timezone=BEIJING_TZ)
    # TODO(Phase D): enumerate user-scoped collection settings and register per-user jobs.
    # A no-user job could select the wrong user's room, so C1 intentionally registers none.
    scheduler.start()
    return scheduler
