from __future__ import annotations

import asyncio
import importlib

import pytest
from fastapi import FastAPI

from app.providers.bupt_auth import AuthErrorKind, AuthFailure
from app.schemas.common import ApiResponse, ErrorCode
from app.services.auth_bootstrap import AppBusinessCookie, AppBusinessSession, BootstrapResult
from app.services.auth_session import AuthSessionManager, SessionAccessError
from app.services.upstream_session_service import UpstreamSessionError, UpstreamSessionStatus


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def business_session(value: str = "test-session") -> AppBusinessSession:
    return AppBusinessSession((
        AppBusinessCookie("eai-sess", value, "app.bupt.edu.cn", "/", None, True),
        AppBusinessCookie("UUkey", f"key-{value}", "app.bupt.edu.cn", "/", None, False),
    ))


class FakeBootstrapService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    async def authenticate(self, username: str, password: str) -> BootstrapResult:
        if self.error:
            raise self.error
        return BootstrapResult(username=username, session=business_session(username))


class FakeRuntimeClient:
    def __init__(self, *, verification: ApiResponse[bool] | None = None) -> None:
        self.verification = verification or ApiResponse.ok(True)
        self.closed = 0

    async def check_auth_result(self) -> ApiResponse[bool]:
        return self.verification

    async def close(self) -> None:
        self.closed += 1


def test_registering_b_does_not_replace_a_and_same_user_reuses_client() -> None:
    runtimes: list[FakeRuntimeClient] = []

    def factory(_: AppBusinessSession) -> FakeRuntimeClient:
        runtime = FakeRuntimeClient()
        runtimes.append(runtime)
        return runtime

    manager = AuthSessionManager(FakeBootstrapService(), factory)  # type: ignore[arg-type]

    async def scenario() -> None:
        a = await manager.bootstrap_login("a", "secret")
        b = await manager.bootstrap_login("b", "secret")
        assert a.data is not None and b.data is not None
        assert (await manager.register_client(1, a.data.session)).success
        assert (await manager.register_client(2, b.data.session)).success
        client_a = await manager.get_client(1)
        client_b = await manager.get_client(2)
        assert client_a is await manager.get_client(1)
        assert client_a is not client_b
        assert runtimes[0].closed == runtimes[1].closed == 0

    run(scenario())


def test_logout_removes_only_requested_user_and_close_all_closes_remaining() -> None:
    runtimes = [FakeRuntimeClient(), FakeRuntimeClient()]
    manager = AuthSessionManager(runtime_client_factory=lambda _: runtimes.pop(0))  # type: ignore[arg-type]

    async def scenario() -> None:
        assert (await manager.register_client(1, business_session("a"))).success
        assert (await manager.register_client(2, business_session("b"))).success
        client_a, client_b = await manager.get_client(1), await manager.get_client(2)
        await manager.remove_client(1)
        assert client_a.closed == 1
        assert client_b.closed == 0
        assert await manager.get_client(2) is client_b
        await manager.close_all()
        assert client_b.closed == 1

    run(scenario())


def test_missing_or_expired_upstream_session_affects_only_that_user() -> None:
    expired_users: list[int] = []

    async def loader(user_id: int) -> AppBusinessSession:
        if user_id == 3:
            raise UpstreamSessionError(UpstreamSessionStatus.REAUTH_REQUIRED)
        return business_session(str(user_id))

    async def mark_reauth(user_id: int) -> None:
        expired_users.append(user_id)

    clients: dict[int, FakeRuntimeClient] = {}

    def factory(session: AppBusinessSession) -> FakeRuntimeClient:
        client = FakeRuntimeClient()
        clients[len(clients) + 1] = client
        return client

    manager = AuthSessionManager(
        runtime_client_factory=factory, runtime_session_loader=loader, runtime_expiry_marker=mark_reauth,
    )  # type: ignore[arg-type]

    async def scenario() -> None:
        client_a = await manager.get_client(1)
        client_b = await manager.get_client(2)
        with pytest.raises(SessionAccessError) as missing:
            await manager.get_client(3)
        assert missing.value.code == ErrorCode.REAUTH_REQUIRED
        client_a.verification = ApiResponse.error(ErrorCode.SESSION_EXPIRED, "expired")
        with pytest.raises(SessionAccessError) as expired:
            async with manager.acquire_client(1):
                pass
        assert expired.value.code == ErrorCode.SESSION_EXPIRED
        assert client_a.closed == 1
        assert client_b.closed == 0
        assert await manager.get_client(2) is client_b
        assert expired_users == [1]

    run(scenario())


def test_same_user_initializes_once_while_different_users_do_not_share_lock() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    factory_calls = 0

    async def loader(user_id: int) -> AppBusinessSession:
        if user_id == 1:
            started.set()
            await release.wait()
        return business_session(str(user_id))

    def factory(_: AppBusinessSession) -> FakeRuntimeClient:
        nonlocal factory_calls
        factory_calls += 1
        return FakeRuntimeClient()

    manager = AuthSessionManager(runtime_client_factory=factory, runtime_session_loader=loader)  # type: ignore[arg-type]

    async def scenario() -> None:
        first_a = asyncio.create_task(manager.get_client(1))
        await started.wait()
        second_a = asyncio.create_task(manager.get_client(1))
        client_b = await asyncio.wait_for(manager.get_client(2), timeout=0.2)
        release.set()
        client_a, duplicate_a = await first_a, await second_a
        assert client_a is duplicate_a
        assert client_a is not client_b
        assert factory_calls == 2

    run(scenario())


def test_login_failure_does_not_create_runtime_client() -> None:
    bootstrap = FakeBootstrapService(error=AuthFailure(AuthErrorKind.CAPTCHA_REQUIRED, "login"))
    manager = AuthSessionManager(bootstrap, lambda _: FakeRuntimeClient())  # type: ignore[arg-type]
    result = run(manager.bootstrap_login("user", "secret"))
    assert not result.success


def test_fastapi_shutdown_calls_close_all(monkeypatch: pytest.MonkeyPatch) -> None:
    main_module = importlib.import_module("app.main")

    class FakeManager:
        def __init__(self, **_: object) -> None:
            self.close_all_calls = 0

        async def close_all(self) -> None:
            self.close_all_calls += 1

    class FakeScheduler:
        def shutdown(self, *, wait: bool) -> None:
            assert wait is False

    manager = FakeManager()

    async def noop() -> None:
        return None

    monkeypatch.setattr(main_module, "init_db", noop)
    monkeypatch.setattr(main_module, "dispose_db", noop)
    monkeypatch.setattr(main_module, "AuthSessionManager", lambda **_: manager)
    monkeypatch.setattr(main_module, "start_collection_scheduler", lambda *_: FakeScheduler())

    async def scenario() -> None:
        async with main_module.lifespan(FastAPI()):
            assert manager.close_all_calls == 0
        assert manager.close_all_calls == 1

    run(scenario())
