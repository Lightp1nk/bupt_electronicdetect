"""Minimal, safe HTTP client for the BUPT CAS-to-app authentication flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup


CHONG_URL = "https://app.bupt.edu.cn/buptdf/wap/default/chong"
PART_URL = "https://app.bupt.edu.cn/buptdf/wap/default/part"


class AuthErrorKind(str, Enum):
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    LOGIN_PAGE_PARSE_ERROR = "LOGIN_PAGE_PARSE_ERROR"
    EXECUTION_NOT_FOUND = "EXECUTION_NOT_FOUND"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    MFA_REQUIRED = "MFA_REQUIRED"
    AUTH_FAILED = "AUTH_FAILED"
    CAS_TICKET_MISSING = "CAS_TICKET_MISSING"
    CAS_CALLBACK_FAILED = "CAS_CALLBACK_FAILED"
    APP_SESSION_FAILED = "APP_SESSION_FAILED"
    BUSINESS_API_FAILED = "BUSINESS_API_FAILED"
    UNEXPECTED_REDIRECT = "UNEXPECTED_REDIRECT"
    CREDENTIALS_REQUIRED = "CREDENTIALS_REQUIRED"


@dataclass(frozen=True)
class AuthResult:
    authenticated: bool
    cookie_names: tuple[str, ...]


@dataclass(frozen=True)
class AuthFailure(Exception):
    kind: AuthErrorKind
    stage: str
    status_code: int | None = None
    current_url: str | None = None
    next_url: str | None = None
    detail: str | None = None

    def __str__(self) -> str:
        fields = [f"error={self.kind.value}", f"stage={self.stage}"]
        if self.status_code is not None:
            fields.append(f"status={self.status_code}")
        if self.current_url:
            fields.append(f"url={_safe_url(self.current_url)}")
        if self.next_url:
            fields.append(f"next={_safe_url(self.next_url)}")
        if self.detail:
            fields.append(self.detail)
        return " | ".join(fields)


CredentialProvider = Callable[[], tuple[str, str] | Awaitable[tuple[str, str]]]
TraceCallback = Callable[[str], None]


def _safe_url(url: str) -> str:
    """Remove sensitive query values before displaying a URL."""
    parts = urlsplit(url)
    sensitive = {"ticket", "execution", "password", "username", "token", "authorization"}
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key.lower() not in sensitive]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


class BUPTAuthClient:
    """Owns one ``httpx.AsyncClient`` for CAS and app business-session cookies."""

    def __init__(
        self,
        *,
        credential_provider: CredentialProvider | None = None,
        trace: TraceCallback | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._client = httpx.AsyncClient(follow_redirects=False, timeout=timeout)
        self._credential_provider = credential_provider
        self._trace = trace

    @property
    def client(self) -> httpx.AsyncClient:
        """The authenticated client to be reused by a later business API client."""
        return self._client

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BUPTAuthClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def login(self, username: str | None = None, password: str | None = None) -> AuthResult:
        """Complete the verified app → CAS → app flow using this client's cookie jar."""
        self._log("[STEP] GET chong")
        response = await self._send("GET", CHONG_URL, stage="GET chong")
        login_url = self._redirect(response, "GET chong")

        response = await self._send("GET", login_url, stage="app login redirect")
        cas_url = self._redirect(response, "app login redirect")

        self._log("[STEP] CAS redirect")
        response = await self._send("GET", cas_url, stage="CAS redirect")
        auth_url = self._redirect(response, "CAS redirect")
        if urlsplit(auth_url).hostname != "auth.bupt.edu.cn":
            raise self._failure(AuthErrorKind.UNEXPECTED_REDIRECT, "CAS redirect", response, auth_url)

        response = await self._send("GET", auth_url, stage="GET authserver")
        if response.is_redirect:
            callback_url = self._redirect(response, "GET authserver")
            self._require_ticket(callback_url, "GET authserver", response)
            self._log("[STEP] CAS ticket received")
        elif response.status_code == 200:
            self._log("[STEP] Login page detected")
            execution = self._execution_from_login_page(response)
            self._log("[STEP] execution found")
            if username is None or password is None:
                username, password = await self._credentials()
            response = await self._send(
                "POST",
                str(response.url),
                stage="POST authserver login",
                data={
                    "username": username,
                    "password": password,
                    "submit": "登录",
                    "type": "username_password",
                    "execution": execution,
                    "_eventId": "submit",
                },
            )
            self._log("[STEP] Login submitted")
            if not response.is_redirect:
                raise self._login_failure(response)
            callback_url = self._redirect(response, "POST authserver login")
            self._require_ticket(callback_url, "POST authserver login", response)
            self._log("[STEP] CAS ticket received")
        else:
            raise self._failure(AuthErrorKind.AUTH_FAILED, "GET authserver", response)

        response = await self._send("GET", callback_url, stage="CAS callback")
        final_url = self._redirect(response, "CAS callback", AuthErrorKind.CAS_CALLBACK_FAILED)
        if not _same_path(final_url, CHONG_URL):
            raise self._failure(AuthErrorKind.CAS_CALLBACK_FAILED, "CAS callback", response, final_url)
        self._log("[STEP] App callback completed")

        response = await self._send("GET", CHONG_URL, stage="verify chong")
        if response.status_code != 200 or not self._is_electricity_page(response):
            raise self._failure(AuthErrorKind.APP_SESSION_FAILED, "verify chong", response)

        if not await self.check_authenticated():
            raise AuthFailure(AuthErrorKind.BUSINESS_API_FAILED, "POST /part")
        return AuthResult(True, self.cookie_names())

    async def check_authenticated(self) -> bool:
        """Verify the app session with the smallest confirmed business API call."""
        response = await self._send("POST", PART_URL, stage="POST /part", data={"areaid": "1"})
        if response.status_code != 200:
            raise self._failure(AuthErrorKind.BUSINESS_API_FAILED, "POST /part", response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise self._failure(AuthErrorKind.BUSINESS_API_FAILED, "POST /part", response, detail="response was not JSON") from exc
        return isinstance(payload, dict) and str(payload.get("e")) == "0"

    def cookie_names(self) -> tuple[str, ...]:
        return tuple(sorted({cookie.name for cookie in self._client.cookies.jar if cookie.domain.lstrip(".") == "app.bupt.edu.cn"}))

    async def _credentials(self) -> tuple[str, str]:
        if self._credential_provider is None:
            raise AuthFailure(AuthErrorKind.CREDENTIALS_REQUIRED, "Login page detected")
        supplied = self._credential_provider()
        if hasattr(supplied, "__await__"):
            supplied = await supplied  # type: ignore[assignment,misc]
        return supplied  # type: ignore[return-value]

    async def _send(self, method: str, url: str, *, stage: str, **kwargs: object) -> httpx.Response:
        try:
            response = await self._client.request(method, url, **kwargs)
            location = response.headers.get("location")
            if location:
                self._log(f"[{response.status_code}] -> {_safe_url(urljoin(str(response.url), location))}")
            else:
                self._log(f"[{response.status_code}] {stage}")
            return response
        except httpx.TimeoutException as exc:
            raise AuthFailure(AuthErrorKind.TIMEOUT, stage, current_url=url) from exc
        except httpx.RequestError as exc:
            raise AuthFailure(AuthErrorKind.NETWORK_ERROR, stage, current_url=url) from exc

    def _redirect(self, response: httpx.Response, stage: str, kind: AuthErrorKind = AuthErrorKind.UNEXPECTED_REDIRECT) -> str:
        location = response.headers.get("location")
        if not response.is_redirect or not location:
            raise self._failure(kind, stage, response)
        return urljoin(str(response.url), location)

    def _require_ticket(self, callback_url: str, stage: str, response: httpx.Response) -> None:
        values = dict(parse_qsl(urlsplit(callback_url).query, keep_blank_values=True))
        if not values.get("ticket"):
            raise self._failure(AuthErrorKind.CAS_TICKET_MISSING, stage, response, callback_url)

    def _execution_from_login_page(self, response: httpx.Response) -> str:
        soup = BeautifulSoup(response.text, "html.parser")
        execution = soup.select_one('input[name="execution"]')
        if execution is None:
            raise self._failure(AuthErrorKind.EXECUTION_NOT_FOUND, "Login page parse", response)
        value = execution.get("value")
        if not isinstance(value, str) or not value:
            raise self._failure(AuthErrorKind.EXECUTION_NOT_FOUND, "Login page parse", response)
        return value

    def _login_failure(self, response: httpx.Response) -> AuthFailure:
        body = response.text.lower()
        if "captcha" in body or "验证码" in response.text:
            kind = AuthErrorKind.CAPTCHA_REQUIRED
        elif "mfa" in body or "多因素" in response.text or "二次验证" in response.text:
            kind = AuthErrorKind.MFA_REQUIRED
        elif response.status_code == 200:
            kind = AuthErrorKind.INVALID_CREDENTIALS
        else:
            kind = AuthErrorKind.AUTH_FAILED
        return self._failure(kind, "POST authserver login", response)

    @staticmethod
    def _is_electricity_page(response: httpx.Response) -> bool:
        url = str(response.url)
        body = response.text.lower()
        return _same_path(url, CHONG_URL) and "authserver" not in url and "name=\"password\"" not in body

    @staticmethod
    def _failure(
        kind: AuthErrorKind,
        stage: str,
        response: httpx.Response,
        next_url: str | None = None,
        detail: str | None = None,
    ) -> AuthFailure:
        return AuthFailure(kind, stage, response.status_code, str(response.url), next_url, detail)

    def _log(self, message: str) -> None:
        if self._trace is not None:
            self._trace(message)


def _same_path(left: str, right: str) -> bool:
    left_parts, right_parts = urlsplit(left), urlsplit(right)
    return left_parts.hostname == right_parts.hostname and left_parts.path == right_parts.path
