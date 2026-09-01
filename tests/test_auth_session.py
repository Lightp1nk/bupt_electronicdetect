from __future__ import annotations

import asyncio

import pytest

from app.providers.bupt_auth import AuthErrorKind, AuthFailure
from app.schemas.common import ApiResponse, ErrorCode
from app.services.auth_bootstrap import AppBusinessCookie, AppBusinessSession, BootstrapResult
from app.services.auth_session import AuthSessionManager, SessionAccessError


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def business_session() -> AppBusinessSession:
    return AppBusinessSession(
        (
            AppBusinessCookie("eai-sess", "test-session", "app.bupt.edu.cn", "/", None, True),
            AppBusinessCookie("UUkey", "test-key", "app.bupt.edu.cn", "/", None, False),
        )
    )


class FakeBootstrapService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def authenticate(self, username: str, password: str) -> BootstrapResult:
        self.calls += 1
        if self.error:
            raise self.error
        return BootstrapResult(username=username, session=business_session())


class FakeRuntimeClient:
    def __init__(self, *, verification: ApiResponse[bool] | None = None) -> None:
        self.verification = verification or ApiResponse.ok(True)
        self.closed = 0

    async def check_auth_result(self) -> ApiResponse[bool]:
        return self.verification

    async def close(self) -> None:
        self.closed += 1


def test_login_replaces_and_closes_old_runtime_client() -> None:
    runtimes = [FakeRuntimeClient(), FakeRuntimeClient()]
    manager = AuthSessionManager(FakeBootstrapService(), lambda _: runtimes.pop(0))  # type: ignore[arg-type]

    first = run(manager.bootstrap_login("user", "secret"))
    assert first.success and first.data is not None
    assert run(manager.activate_runtime(1, first.data.session)).success
    old = manager.get_client()
    second = run(manager.bootstrap_login("user", "secret"))
    assert second.success and second.data is not None
    assert run(manager.activate_runtime(1, second.data.session)).success
    assert old is not None and old.closed == 1
    assert manager.get_client() is not old
    assert not hasattr(manager, "_username")
    assert not hasattr(manager, "_password")


def test_login_failure_does_not_create_runtime_client() -> None:
    bootstrap = FakeBootstrapService(error=AuthFailure(AuthErrorKind.CAPTCHA_REQUIRED, "login"))
    created = False

    def runtime(_: AppBusinessSession) -> FakeRuntimeClient:
        nonlocal created
        created = True
        return FakeRuntimeClient()

    manager = AuthSessionManager(bootstrap, runtime)  # type: ignore[arg-type]
    result = run(manager.bootstrap_login("user", "secret"))
    assert not result.success
    assert manager.get_client() is None
    assert created is False


def test_status_expiry_clears_runtime_client() -> None:
    expired = FakeRuntimeClient(verification=ApiResponse.error(ErrorCode.SESSION_EXPIRED, "expired"))
    manager = AuthSessionManager(FakeBootstrapService(), lambda _: expired)  # type: ignore[arg-type]
    logged_in = run(manager.bootstrap_login("user", "secret"))
    assert logged_in.data is not None
    run(manager.activate_runtime(1, logged_in.data.session))
    result = run(manager.status())
    assert result.success and result.data.authenticated is False
    assert result.data.state.value == "SESSION_EXPIRED"
    assert manager.get_client() is None
    assert expired.closed == 1


def test_logout_and_unlogged_access() -> None:
    runtime = FakeRuntimeClient()
    manager = AuthSessionManager(FakeBootstrapService(), lambda _: runtime)  # type: ignore[arg-type]
    assert run(manager.status()).data.authenticated is False
    logged_in = run(manager.bootstrap_login("user", "secret"))
    assert logged_in.data is not None
    run(manager.activate_runtime(1, logged_in.data.session))
    assert run(manager.logout()).success
    assert runtime.closed == 1

    async def access() -> None:
        async with manager.acquire_client():
            raise AssertionError("should not yield")

    with pytest.raises(SessionAccessError) as error:
        run(access())
    assert error.value.code == ErrorCode.AUTH_REQUIRED


def test_business_lease_marks_user_upstream_session_expired_after_request() -> None:
    class ExpiringRuntime(FakeRuntimeClient):
        def __init__(self) -> None:
            super().__init__()
            self.checks = 0

        async def check_auth_result(self) -> ApiResponse[bool]:
            self.checks += 1
            return ApiResponse.ok(True) if self.checks == 1 else ApiResponse.error(ErrorCode.SESSION_EXPIRED, "expired")

    expired_users: list[int] = []

    async def load(_: int) -> AppBusinessSession:
        return business_session()

    async def mark_expired(user_id: int) -> None:
        expired_users.append(user_id)

    runtime = ExpiringRuntime()
    manager = AuthSessionManager(
        runtime_client_factory=lambda _: runtime, runtime_session_loader=load, runtime_expiry_marker=mark_expired,
    )  # type: ignore[arg-type]

    async def lease() -> None:
        async with manager.acquire_client(7):
            pass

    run(lease())
    assert expired_users == [7]
    assert runtime.closed == 1
    assert manager.get_client(7) is None
