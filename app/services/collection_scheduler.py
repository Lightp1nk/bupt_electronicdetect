"""APScheduler lifecycle helpers for this single-process FastAPI application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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
    """Schedule one Beijing-time job. V1 assumes one FastAPI process and one worker."""
    scheduler = AsyncIOScheduler(timezone=BEIJING_TZ)
    if config.enabled:
        scheduler.add_job(
            service.run_once,
            trigger=CronTrigger(hour=config.hour, minute=config.minute, timezone=BEIJING_TZ),
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=15 * 60,
        )
    scheduler.start()
    return scheduler
