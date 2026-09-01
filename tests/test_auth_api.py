from __future__ import annotations

import asyncio

import httpx
from app.main import app
from app.schemas.common import ApiResponse
from app.services.auth_bootstrap import AppBusinessCookie, AppBusinessSession, BootstrapResult
from app.services.auth_session import AuthSessionManager
from app.services.collection_scheduler import JOB_ID


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self) -> None:
        self.closed = 0
        FakeClient.instances.append(self)

    async def login(self, username: str, password: str) -> None:
        return None

    async def check_auth_result(self) -> ApiResponse[bool]:
        return ApiResponse.ok(True)

    async def get_buildings(self, *, area_id: str) -> ApiResponse[list[object]]:
        return ApiResponse.ok([])

    async def get_floors(self, *, area_id: str, building_id: str) -> ApiResponse[list[object]]:
        return ApiResponse.ok([])

    async def get_rooms(self, *, area_id: str, building_id: str, floor_id: str) -> ApiResponse[list[object]]:
        return ApiResponse.ok([])

    async def close(self) -> None:
        self.closed += 1


class FakeBootstrapService:
    async def authenticate(self, username: str, password: str) -> BootstrapResult:
        return BootstrapResult(
            username=username,
            session=AppBusinessSession(
                (
                    AppBusinessCookie("eai-sess", "test-session", "app.bupt.edu.cn", "/", None, True),
                    AppBusinessCookie("UUkey", "test-key", "app.bupt.edu.cn", "/", None, False),
                )
            ),
        )


def fake_manager() -> AuthSessionManager:
    return AuthSessionManager(FakeBootstrapService(), lambda _: FakeClient())  # type: ignore[arg-type]


def test_auth_routes_reuse_then_clear_session() -> None:
    FakeClient.instances.clear()

    async def scenario() -> None:
        app.state.auth_session_manager = fake_manager()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = await client.get("/api/v1/auth/status")
            login = await client.post("/api/v1/auth/login", json={"username": "user", "password": "secret"})
            active = await client.get("/api/v1/auth/status")
            first = await client.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            second = await client.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            floors = await client.get("/api/v1/electricity/floors", params={"area_id": "1", "building_id": "b"})
            rooms = await client.get("/api/v1/electricity/rooms", params={"area_id": "1", "building_id": "b", "floor_id": "f"})
            logout = await client.post("/api/v1/auth/logout")
            protected = await client.get("/api/v1/electricity/buildings", params={"area_id": "1"})
        assert before.json()["data"]["authenticated"] is False
        assert login.json()["success"] is True
        assert active.json()["data"]["authenticated"] is True
        assert first.json()["success"] is True
        assert second.json()["success"] is True
        assert floors.json()["success"] is True
        assert rooms.json()["success"] is True
        assert logout.json()["success"] is True
        assert protected.status_code == 401
        assert protected.json()["code"] == "AUTH_REQUIRED"

    asyncio.run(scenario())
    assert len(FakeClient.instances) == 1


def test_lifespan_shutdown_closes_client() -> None:
    FakeClient.instances.clear()

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            scheduler = app.state.collection_scheduler
            assert scheduler.get_job(JOB_ID) is not None
            assert len([job for job in scheduler.get_jobs() if job.id == JOB_ID]) == 1
            app.state.auth_session_manager = fake_manager()
            result = await app.state.auth_session_manager.login("user", "secret")
            assert result.success

    asyncio.run(scenario())
    assert FakeClient.instances[0].closed == 1
