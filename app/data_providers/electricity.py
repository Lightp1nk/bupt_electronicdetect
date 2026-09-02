"""Read-only real and demonstration electricity history providers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.electricity import ElectricityRecordRead


class ElectricityDataProvider(Protocol):
    """Minimal read interface shared by real and demonstration dashboard data."""

    async def get_latest(self, area_id: str, room_id: str) -> ElectricityRecordRead | None: ...

    async def get_history(
        self, area_id: str, room_id: str, *, since: datetime | None = None, limit: int | None = None,
    ) -> Sequence[ElectricityRecordRead]: ...


class RealElectricityDataProvider:
    """Adapter over immutable production snapshots; this class never writes."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = ElectricityRepository(session)

    async def get_latest(self, area_id: str, room_id: str) -> ElectricityRecordRead | None:
        record = await self._repository.get_latest(area_id, room_id)
        return ElectricityRecordRead.model_validate(record) if record is not None else None

    async def get_history(
        self, area_id: str, room_id: str, *, since: datetime | None = None, limit: int | None = None,
    ) -> Sequence[ElectricityRecordRead]:
        records = await self._repository.get_history(area_id, room_id, since=since, limit=limit)
        return [ElectricityRecordRead.model_validate(record) for record in records]


class DemoElectricityDataProvider:
    """Static JSON dataset for read-only visual demonstrations.

    It intentionally has no database session, provider client, scheduler hook, or
    alert/notification dependency.  The canonical demo room is returned for the
    explicit ``source=demo`` dashboard requests only.
    """

    _dataset_path = Path(__file__).resolve().parent.parent / "demo_data" / "demo_electricity_history.json"

    def __init__(self, records: Sequence[ElectricityRecordRead] | None = None) -> None:
        self._records = tuple(records) if records is not None else self._load_records()

    async def get_latest(self, area_id: str, room_id: str) -> ElectricityRecordRead | None:
        records = await self.get_history(area_id, room_id)
        return records[-1] if records else None

    async def get_history(
        self, area_id: str, room_id: str, *, since: datetime | None = None, limit: int | None = None,
    ) -> Sequence[ElectricityRecordRead]:
        records = list(self._records)
        if since is not None:
            records = [record for record in records if (record.source_time or record.query_time) >= since]
        if limit is not None:
            records = records[-limit:]
        return records

    @classmethod
    def _load_records(cls) -> tuple[ElectricityRecordRead, ...]:
        payload = json.loads(cls._dataset_path.read_text(encoding="utf-8"))
        room = payload["room"]
        records: list[ElectricityRecordRead] = []
        for index, item in enumerate(payload["records"], start=1):
            moment = datetime.fromisoformat(item["source_time"])
            records.append(ElectricityRecordRead(
                id=index,
                area_id=room["area_id"], building_id=room["building_id"], building_name=room["building_name"],
                floor_id=room["floor_id"], floor_name=room["floor_name"], room_id=room["room_id"], room_name=room["room_name"],
                remaining_money=item["remaining_money"], remaining_kwh=item["remaining_kwh"],
                remaining_energy_kwh=None, free_remaining_kwh=None, total_usage_kwh=item["total_usage_kwh"],
                price_per_kwh=None, source_time=moment, query_time=moment, created_at=moment,
                raw_data_json={"dataset": "demo", "scenario": item.get("scenario", "normal")},
            ))
        return tuple(records)
