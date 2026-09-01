from __future__ import annotations

import asyncio

import pytest

import app.services.auth_session as session_module
from app.schemas.common import ApiResponse, ErrorCode
from app.services.auth_session import AuthSessionManager, SessionAccessError


class FakeClient:
    def __init__(self, *, login_error: Exception | None = None, verification: ApiResponse[bool] | None = None) -> None:
        self.login_error = login_error
        self.verification = verification or ApiResponse.ok(True)
        self.closed = 0
        self.login_calls = 0

    async def login(self, username: str, password: str) -> None:
        self.login_calls += 1
        if self.login_error:
            raise self.login_error

    async def check_auth_result(self) -> ApiResponse[bool]:
        return self.verification

    async def close(self) -> None:
        self.closed += 1


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def test_login_replaces_and_closes_old_client(monkeypatch: pytest.MonkeyPatch) -> None:
    clients = [FakeClient(), FakeClient()]
    monkeypatch.setattr(session_module, "BUPTClient", lambda: clients.pop(0))
    manager = AuthSessionManager()

    assert run(manager.login("user", "secret")).success
    old = manager.get_client()
    assert run(manager.login("user", "secret")).success
    assert old.closed == 1
    assert manager.get_client() is not old
    assert not hasattr(manager, "_username")
    assert not hasattr(manager, "_password")


def test_login_failure_closes_failed_client(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = FakeClient(login_error=RuntimeError("no details exposed"))
    monkeypatch.setattr(session_module, "BUPTClient", lambda: failed)
    manager = AuthSessionManager()
    result = run(manager.login("user", "secret"))
    assert not result.success
    assert manager.get_client() is None
    assert failed.closed == 1


def test_status_expiry_clears_client(monkeypatch: pytest.MonkeyPatch) -> None:
    expired = FakeClient(verification=ApiResponse.error(ErrorCode.SESSION_EXPIRED, "expired"))
    monkeypatch.setattr(session_module, "BUPTClient", lambda: expired)
    manager = AuthSessionManager()
    run(manager.login("user", "secret"))
    result = run(manager.status())
    assert result.success and result.data.authenticated is False
    assert result.data.state.value == "SESSION_EXPIRED"
    assert manager.get_client() is None
    assert expired.closed == 1


def test_logout_and_unlogged_access(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClient()
    monkeypatch.setattr(session_module, "BUPTClient", lambda: fake)
    manager = AuthSessionManager()
    assert run(manager.status()).data.authenticated is False
    run(manager.login("user", "secret"))
    assert run(manager.logout()).success
    assert fake.closed == 1

    async def access() -> None:
        async with manager.acquire_client():
            raise AssertionError("should not yield")

    with pytest.raises(SessionAccessError) as error:
        run(access())
    assert error.value.code == ErrorCode.AUTH_REQUIRED
