"""One timezone-aware scheduler job for all user-scoped collection settings."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.collection_repository import CollectionRepository
from app.services.collection_service import CollectionService


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
JOB_ID = "daily-electricity-collection"
MISFIRE_GRACE_SECONDS = 300
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionScheduleConfig:
    enabled: bool = True
    hour: int = 4
    minute: int = 0
    max_concurrency: int = 3

    @classmethod
    def from_environment(cls) -> "CollectionScheduleConfig":
        enabled = _environment_bool("COLLECTION_ENABLED", "ELECTRICITY_COLLECTION_ENABLED", default=True)
        hour = _environment_int("COLLECTION_HOUR", "ELECTRICITY_COLLECTION_HOUR", default=4)
        minute = _environment_int("COLLECTION_MINUTE", "ELECTRICITY_COLLECTION_MINUTE", default=0)
        max_concurrency = _environment_int("COLLECTION_MAX_CONCURRENCY", default=3)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError("collection hour/minute must form a valid local time")
        if max_concurrency < 1:
            raise ValueError("collection max concurrency must be positive")
        return cls(enabled=enabled, hour=hour, minute=minute, max_concurrency=max_concurrency)


class MultiUserCollectionScheduler:
    """Enumerate enabled users once per run and isolate every collection task."""

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        collection_service: CollectionService,
        *,
        max_concurrency: int,
    ) -> None:
        self._session_factory = session_factory
        self._collection_service = collection_service
        self._max_concurrency = max_concurrency

    async def run_all_once(self) -> None:
        try:
            async with self._session_factory() as session:
                user_ids = await CollectionRepository(session).list_enabled_user_ids()
        except SQLAlchemyError:
            logger.exception("could not enumerate users for scheduled collection")
            return

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def run_user(user_id: int) -> None:
            async with semaphore:
                try:
                    await self._collection_service.run_once(user_id)
                except Exception:
                    # Do not include upstream messages: they could contain sensitive data.
                    logger.exception("scheduled collection failed for user_id=%s", user_id)

        await asyncio.gather(*(run_user(user_id) for user_id in user_ids))


def start_collection_scheduler(
    collection_scheduler: MultiUserCollectionScheduler,
    config: CollectionScheduleConfig,
) -> AsyncIOScheduler:
    """Start one daily job; V1 is intentionally single process/single worker."""
    scheduler = AsyncIOScheduler(timezone=BEIJING_TZ)
    if config.enabled:
        scheduler.add_job(
            collection_scheduler.run_all_once,
            CronTrigger(hour=config.hour, minute=config.minute, timezone=BEIJING_TZ),
            id=JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=MISFIRE_GRACE_SECONDS,
        )
    scheduler.start()
    return scheduler


def _environment_bool(primary: str, legacy: str | None = None, *, default: bool) -> bool:
    value = os.getenv(primary, os.getenv(legacy, str(default)) if legacy else str(default))
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _environment_int(primary: str, legacy: str | None = None, *, default: int) -> int:
    return int(os.getenv(primary, os.getenv(legacy, str(default)) if legacy else str(default)))
