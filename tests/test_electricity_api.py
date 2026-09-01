from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_authenticated_bupt_client
from app.database.database import Base, get_db_session
from app.main import app
from app.models import electricity  # noqa: F401
from app.schemas.common import ApiResponse
from app.schemas.electricity import ElectricityReading
from app.services.auth_session import AuthSessionManager


class FakeUpstreamClient:
    async def query_electricity(self, **_: object) -> ApiResponse[ElectricityReading]:
        return ApiResponse.ok(ElectricityReading(
            area_id="2", building_id="b", floor_id="f", room_id="r", room_name="203",
            source_time="2026-09-01 15:00:00", remaining_money=47.14, raw_data={"surplus": "47.14"},
        ))


class LoggedInManager:
    @asynccontextmanager
    async def acquire_client(self):
        yield FakeUpstreamClient()


def test_query_requires_login_and_history_reads_local_db(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'api.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_session():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_db_session] = override_session
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            app.state.auth_session_manager = AuthSessionManager()
            unauthorized = await client.post("/api/v1/electricity/query", json={
                "area_id": "2", "building_id": "b", "floor_id": "f", "room_id": "r"
            })
            app.state.auth_session_manager = LoggedInManager()
            queried = await client.post("/api/v1/electricity/query", json={
                "area_id": "2", "building_id": "b", "floor_id": "f", "room_id": "r", "room_name": "203"
            })
            history = await client.get("/api/v1/electricity/history/r", params={"area_id": "2"})
            latest = await client.get("/api/v1/electricity/latest/r", params={"area_id": "2"})
            analysis = await client.get("/api/v1/electricity/analysis/r", params={"area_id": "2"})
            wrong_area = await client.get("/api/v1/electricity/analysis/r", params={"area_id": "1"})
        assert unauthorized.status_code == 401
        assert unauthorized.json()["code"] == "AUTH_REQUIRED"
        assert queried.status_code == 200
        assert queried.json()["data"]["saved"] is True
        assert len(history.json()["data"]) == 1
        assert latest.json()["data"]["room_id"] == "r"
        assert analysis.status_code == 200
        assert analysis.json()["data"]["statistics"]["valid_daily_count"] == 0
        assert analysis.json()["data"]["prediction"]["maturity"] == "insufficient"
        assert wrong_area.status_code == 404
        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(scenario())
