"""Short-lived CAS bootstrap and app-only runtime-session construction."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar
from typing import Any

from app.providers.bupt_auth import AuthErrorKind, AuthFailure
from app.providers.bupt_client import BUPTClient


APP_HOST = "app.bupt.edu.cn"
APP_COOKIE_NAMES = frozenset({"eai-sess", "UUkey"})


@dataclass(frozen=True)
class AppBusinessCookie:
    """The minimum metadata needed to recreate one app-domain cookie."""

    name: str
    value: str
    domain: str
    path: str
    expires: int | None
    secure: bool


@dataclass(frozen=True)
class AppBusinessSession:
    """Verified, allowlisted business-session cookies without CAS state."""

    cookies: tuple[AppBusinessCookie, ...]

    def __post_init__(self) -> None:
        names = {cookie.name for cookie in self.cookies}
        if names != APP_COOKIE_NAMES or len(self.cookies) != len(APP_COOKIE_NAMES):
            raise ValueError("app business session must contain exactly the required app cookies")
        for cookie in self.cookies:
            if not _is_app_cookie_domain(cookie.domain) or not cookie.path.startswith("/"):
                raise ValueError("app business session contains an invalid cookie scope")

    @classmethod
    def from_cookiejar(cls, cookies: Iterable[Cookie]) -> "AppBusinessSession":
        allowed = [cookie for cookie in cookies if cookie.name in APP_COOKIE_NAMES]
        if any(not _is_app_cookie_domain(cookie.domain) for cookie in allowed):
            raise ValueError("required app cookie has an invalid domain")
        try:
            return cls(
                tuple(
                    AppBusinessCookie(
                        name=cookie.name,
                        value=cookie.value,
                        domain=cookie.domain,
                        path=cookie.path,
                        expires=cookie.expires if isinstance(cookie.expires, int) else None,
                        secure=cookie.secure,
                    )
                    for cookie in allowed
                )
            )
        except ValueError:
            raise

    def install_into(self, jar: CookieJar) -> None:
        """Install only this value object's allowlisted cookies into an empty jar."""
        for cookie in self.cookies:
            jar.set_cookie(
                Cookie(
                    version=0,
                    name=cookie.name,
                    value=cookie.value,
                    port=None,
                    port_specified=False,
                    domain=cookie.domain,
                    domain_specified=True,
                    domain_initial_dot=cookie.domain.startswith("."),
                    path=cookie.path,
                    path_specified=True,
                    secure=cookie.secure,
                    expires=cookie.expires,
                    discard=cookie.expires is None,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                )
            )


@dataclass(frozen=True)
class BootstrapResult:
    username: str
    session: AppBusinessSession


class AuthBootstrapService:
    """Perform CAS with a temporary client, then return only app session material."""

    def __init__(self, client_factory: Callable[[], BUPTClient] = BUPTClient) -> None:
        self._client_factory = client_factory

    async def authenticate(self, username: str, password: str) -> BootstrapResult:
        bootstrap_client = self._client_factory()
        try:
            await bootstrap_client.login(username, password)
            try:
                session = AppBusinessSession.from_cookiejar(bootstrap_client.client.cookies.jar)
            except ValueError as exc:
                raise AuthFailure(AuthErrorKind.APP_SESSION_FAILED, "extract app business session") from exc
            return BootstrapResult(username=username, session=session)
        finally:
            await bootstrap_client.close()


def create_runtime_client(
    session: AppBusinessSession, *, client_factory: Callable[[], BUPTClient] = BUPTClient
) -> BUPTClient:
    """Build a new provider client whose jar contains only app business cookies."""
    client = client_factory()
    session.install_into(client.client.cookies.jar)
    return client


def _is_app_cookie_domain(domain: str) -> bool:
    normalized = domain.lower()
    return normalized in {APP_HOST, f".{APP_HOST}"}
