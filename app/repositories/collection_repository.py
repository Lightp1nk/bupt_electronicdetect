"""User-scoped data access for automatic-collection configuration."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import CollectionSettings
from app.models.user import User


class CollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_settings(self, user_id: int) -> CollectionSettings | None:
        return await self._session.scalar(select(CollectionSettings).where(CollectionSettings.user_id == user_id))

    async def list_enabled_user_ids(self) -> list[int]:
        """Return only real users with a complete, enabled monitored room.

        The legacy unassigned table is intentionally never referenced here.
        Joining users also prevents an orphaned SQLite row from being scheduled.
        """
        statement = (
            select(CollectionSettings.user_id)
            .join(User, User.id == CollectionSettings.user_id)
            .where(
                CollectionSettings.enabled.is_(True),
                CollectionSettings.area_id.is_not(None),
                CollectionSettings.building_id.is_not(None),
                CollectionSettings.floor_id.is_not(None),
                CollectionSettings.room_id.is_not(None),
            )
            .order_by(CollectionSettings.user_id)
        )
        return list((await self._session.scalars(statement)).all())

    async def update_settings(
        self, user_id: int, *, area_id: str, area_name: str, building_id: str, building_name: str,
        floor_id: str, floor_name: str, room_id: str, room_name: str,
    ) -> CollectionSettings:
        settings = await self.get_settings(user_id)
        if settings is None:
            settings = CollectionSettings(user_id=user_id)
            self._session.add(settings)
        settings.area_id, settings.area_name = area_id, area_name
        settings.building_id, settings.building_name = building_id, building_name
        settings.floor_id, settings.floor_name = floor_id, floor_name
        settings.room_id, settings.room_name = room_id, room_name
        await self._session.flush()
        return settings

    async def clear_settings(self, user_id: int) -> None:
        settings = await self.get_settings(user_id)
        if settings is not None:
            await self._session.delete(settings)

    async def update_status(
        self, user_id: int, *, status: str, message: str | None, attempted_at: datetime | None = None,
        succeeded_at: datetime | None = None, source_time: datetime | None = None,
    ) -> CollectionSettings | None:
        settings = await self.get_settings(user_id)
        if settings is None:
            return None
        settings.status, settings.message = status, message
        if attempted_at is not None:
            settings.last_attempt_time = attempted_at
        if succeeded_at is not None:
            settings.last_success_time = succeeded_at
        if source_time is not None:
            settings.last_source_time = source_time
        return settings
