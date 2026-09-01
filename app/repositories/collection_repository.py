"""Repository for the one and only automatic-collection configuration row."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import CollectionSettings


class CollectionRepository:
    SINGLETON_ID = 1

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current_settings(self) -> CollectionSettings:
        settings = await self._session.get(CollectionSettings, self.SINGLETON_ID)
        if settings is None:
            settings = CollectionSettings(id=self.SINGLETON_ID)
            self._session.add(settings)
            await self._session.flush()
        return settings

    async def update_current_room(
        self, *, area_id: str, building_id: str, building_name: str, floor_id: str, floor_name: str, room_id: str, room_name: str
    ) -> CollectionSettings:
        settings = await self.get_current_settings()
        settings.area_id, settings.building_id, settings.building_name = area_id, building_id, building_name
        settings.floor_id, settings.floor_name = floor_id, floor_name
        settings.room_id, settings.room_name = room_id, room_name
        return settings

    async def clear_current_room(self) -> CollectionSettings:
        settings = await self.get_current_settings()
        settings.area_id = settings.building_id = settings.building_name = None
        settings.floor_id = settings.floor_name = settings.room_id = settings.room_name = None
        return settings

    async def update_current_status(
        self, *, status: str, message: str | None, attempted_at: datetime | None = None,
        succeeded_at: datetime | None = None, source_time: datetime | None = None,
    ) -> CollectionSettings:
        settings = await self.get_current_settings()
        settings.status, settings.message = status, message
        if attempted_at is not None:
            settings.last_attempt_time = attempted_at
        if succeeded_at is not None:
            settings.last_success_time = succeeded_at
        if source_time is not None:
            settings.last_source_time = source_time
        return settings
