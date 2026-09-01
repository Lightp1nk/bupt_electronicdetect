"""CRUD operations for immutable electricity snapshots."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.electricity import ElectricityRecord
from app.schemas.electricity import ElectricityReading


class ElectricityRepository:
    """Repository methods never commit; the service owns transaction boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_source_time(self, area_id: str, room_id: str, source_time: datetime) -> ElectricityRecord | None:
        statement = select(ElectricityRecord).where(
            ElectricityRecord.area_id == area_id,
            ElectricityRecord.room_id == room_id,
            ElectricityRecord.source_time == source_time,
        )
        return await self._session.scalar(statement)

    async def add(self, reading: ElectricityReading, *, source_time: datetime | None, query_time: datetime) -> ElectricityRecord:
        record = ElectricityRecord(
            area_id=reading.area_id,
            building_id=reading.building_id,
            building_name=reading.building_name,
            floor_id=reading.floor_id,
            floor_name=reading.floor_name,
            room_id=reading.room_id,
            room_name=reading.room_name,
            remaining_money=reading.remaining_money,
            remaining_kwh=reading.remaining_kwh,
            remaining_energy_kwh=reading.remaining_energy_kwh,
            free_remaining_kwh=reading.free_remaining_kwh,
            total_usage_kwh=reading.total_usage_kwh,
            price_per_kwh=reading.price_per_kwh,
            source_time=source_time,
            query_time=query_time,
            created_at=query_time,
            raw_data_json=reading.raw_data,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get_latest(self, area_id: str, room_id: str) -> ElectricityRecord | None:
        statement = self._time_ordered(
            select(ElectricityRecord).where(ElectricityRecord.area_id == area_id, ElectricityRecord.room_id == room_id), descending=True
        ).limit(1)
        return await self._session.scalar(statement)

    async def get_history(
        self, area_id: str, room_id: str, *, since: datetime | None = None, limit: int | None = None
    ) -> list[ElectricityRecord]:
        statement: Select[tuple[ElectricityRecord]] = select(ElectricityRecord).where(
            ElectricityRecord.area_id == area_id, ElectricityRecord.room_id == room_id
        )
        time_value = func.coalesce(ElectricityRecord.source_time, ElectricityRecord.query_time)
        if since is not None:
            statement = statement.where(time_value >= since)
        if limit is None:
            statement = statement.order_by(time_value.asc(), ElectricityRecord.id.asc())
            return list((await self._session.scalars(statement)).all())
        statement = statement.order_by(time_value.desc(), ElectricityRecord.id.desc()).limit(limit)
        return list(reversed((await self._session.scalars(statement)).all()))

    @staticmethod
    def _time_ordered(statement: Select[tuple[ElectricityRecord]], *, descending: bool) -> Select[tuple[ElectricityRecord]]:
        time_value = func.coalesce(ElectricityRecord.source_time, ElectricityRecord.query_time)
        order = time_value.desc() if descending else time_value.asc()
        return statement.order_by(order, ElectricityRecord.id.desc() if descending else ElectricityRecord.id.asc())
