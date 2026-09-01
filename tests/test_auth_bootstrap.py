from __future__ import annotations

import asyncio
from http.cookiejar import Cookie

import httpx
import pytest

from app.providers.bupt_auth import AuthErrorKind, AuthFailure
from app.providers.bupt_client import BUPTClient
from app.services.auth_bootstrap import APP_COOKIE_NAMES, AppBusinessSession, AuthBootstrapService, create_runtime_client


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def add_cookie(client: httpx.AsyncClient, name: str, value: str, domain: str, *, secure: bool = False) -> None:
    client.cookies.jar.set_cookie(
        Cookie(0, name, value, None, False, domain, True, domain.startswith("."), "/", True, secure, None, True, None, None, {}, False)
    )


class FakeBootstrapClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.client = httpx.AsyncClient()
        self.error = error
        self.closed = 0
        add_cookie(self.client, "eai-sess", "session-value", "app.bupt.edu.cn", secure=True)
        add_cookie(self.client, "UUkey", "key-value", "app.bupt.edu.cn")
        add_cookie(self.client, "CASTGC", "cas-value", "auth.bupt.edu.cn", secure=True)

    async def login(self, username: str, password: str) -> None:
        if self.error:
            raise self.error

    async def close(self) -> None:
        self.closed += 1
        await self.client.aclose()


def test_bootstrap_extracts_only_app_business_session_and_closes_client() -> None:
    bootstrap = FakeBootstrapClient()
    result = run(AuthBootstrapService(lambda: bootstrap).authenticate("user", "secret"))
    assert result.username == "user"
    assert {cookie.name for cookie in result.session.cookies} == APP_COOKIE_NAMES
    assert bootstrap.closed == 1
    assert bootstrap.client.is_closed


def test_invalid_or_missing_business_cookies_are_rejected() -> None:
    client = httpx.AsyncClient()
    add_cookie(client, "eai-sess", "session-value", "auth.bupt.edu.cn")
    with pytest.raises(ValueError):
        AppBusinessSession.from_cookiejar(client.cookies.jar)
    run(client.aclose())


def test_runtime_client_is_new_and_uses_only_allowlisted_cookies() -> None:
    bootstrap = FakeBootstrapClient()
    result = run(AuthBootstrapService(lambda: bootstrap).authenticate("user", "secret"))

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/part")
        return httpx.Response(200, json={"e": 0, "d": {"data": []}})

    runtime = create_runtime_client(result.session, client_factory=lambda: BUPTClient(transport=httpx.MockTransport(handler)))
    try:
        assert runtime is not bootstrap
        assert {cookie.name for cookie in runtime.client.cookies.jar} == APP_COOKIE_NAMES
        assert {cookie.domain.lstrip(".") for cookie in runtime.client.cookies.jar} == {"app.bupt.edu.cn"}
        assert run(runtime.get_buildings(area_id="1")).success
    finally:
        run(runtime.close())


def test_captcha_failure_is_preserved_and_bootstrap_client_is_closed() -> None:
    captcha = AuthFailure(AuthErrorKind.CAPTCHA_REQUIRED, "POST authserver login")
    bootstrap = FakeBootstrapClient(error=captcha)
    with pytest.raises(AuthFailure) as error:
        run(AuthBootstrapService(lambda: bootstrap).authenticate("user", "secret"))
    assert error.value.kind == AuthErrorKind.CAPTCHA_REQUIRED
    assert bootstrap.closed == 1


def test_bootstrap_emits_no_cookie_or_credential_logs(caplog: pytest.LogCaptureFixture) -> None:
    bootstrap = FakeBootstrapClient()
    run(AuthBootstrapService(lambda: bootstrap).authenticate("user", "secret"))
    assert "session-value" not in caplog.text
    assert "key-value" not in caplog.text
    assert "secret" not in caplog.text
