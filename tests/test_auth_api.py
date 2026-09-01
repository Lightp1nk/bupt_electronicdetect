from __future__ import annotations

import asyncio

import httpx
import pytest

import app.services.auth_session as session_module
from app.main import app
from app.schemas.common import ApiResponse
from app.services.auth_session import AuthSessionManager


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

    async def close(self) -> None:
        self.closed += 1


def test_auth_routes_reuse_then_clear_session(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.instances.clear()
    monkeypatch.setattr(session_module, "BUPTClient", FakeClient)

    async def scenario() -> None:
        app.state.auth_session_manager = AuthSessionManager()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            before = await client.get("/api/v1/auth/status")
            login = await client.post("/api/v1/auth/login", json={"username": "user", "password": "secret"})
            active = await client.get("/api/v1/auth/status")
            first = await client.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            second = await client.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            logout = await client.post("/api/v1/auth/logout")
            protected = await client.get("/api/v1/electricity/buildings", params={"area_id": "1"})
        assert before.json()["data"]["authenticated"] is False
        assert login.json()["success"] is True
        assert active.json()["data"]["authenticated"] is True
        assert first.json()["success"] is True
        assert second.json()["success"] is True
        assert logout.json()["success"] is True
        assert protected.status_code == 401
        assert protected.json()["code"] == "AUTH_REQUIRED"

    asyncio.run(scenario())
    assert len(FakeClient.instances) == 1


def test_lifespan_shutdown_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.instances.clear()
    monkeypatch.setattr(session_module, "BUPTClient", FakeClient)

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            result = await app.state.auth_session_manager.login("user", "secret")
            assert result.success

    asyncio.run(scenario())
    assert FakeClient.instances[0].closed == 1
