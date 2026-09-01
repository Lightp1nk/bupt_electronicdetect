from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_user
from app.database.database import Base, get_db_session
from app.main import app
from app.models import alert, collection, electricity, upstream_session, user  # noqa: F401
from app.services.collection_service import CollectionService
from app.services.monitoring_service import MonitoringService


class FakeManager:
    def has_client(self, user_id: int) -> bool:
        return False


def test_collection_api_uses_current_user_without_accepting_user_id(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'api.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_session():
            async with sessions() as session:
                yield session

        current = {"id": 1}
        app.dependency_overrides[get_db_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=current["id"])
        app.state.collection_service = CollectionService(sessions, FakeManager(), MonitoringService(), enabled=True, hour=4, minute=0)
        payload_a = {"area_id": "2", "area_name": "沙河", "building_id": "a", "building_name": "A楼", "floor_id": "1", "floor_name": "1层", "room_id": "101", "room_name": "101"}
        payload_b = {**payload_a, "building_id": "b", "building_name": "B楼", "room_id": "202", "room_name": "202"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.put("/api/v1/electricity/collection/settings", json=payload_a)).status_code == 200
            current["id"] = 2
            assert (await client.put("/api/v1/electricity/collection/settings", json=payload_b)).status_code == 200
            assert (await client.get("/api/v1/electricity/collection/settings")).json()["data"]["room_id"] == "202"
            current["id"] = 1
            assert (await client.get("/api/v1/electricity/collection/settings")).json()["data"]["room_id"] == "101"
            assert (await client.delete("/api/v1/electricity/collection/settings")).status_code == 200
            current["id"] = 2
            assert (await client.get("/api/v1/electricity/collection/settings")).json()["data"]["room_id"] == "202"

        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(scenario())
