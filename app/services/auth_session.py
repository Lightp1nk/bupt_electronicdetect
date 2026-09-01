"""In-memory lifecycle manager for the sole BUPT client in this local app."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from app.providers.bupt_auth import AuthErrorKind, AuthFailure
from app.providers.bupt_client import BUPTClient
from app.schemas.auth import SessionState, SessionStatus
from app.schemas.common import ApiResponse, ErrorCode
from app.services.auth_bootstrap import AppBusinessSession, AuthBootstrapService, create_runtime_client


@dataclass(frozen=True)
class SessionAccessError(Exception):
    code: ErrorCode
    message: str


class AuthSessionManager:
    """Own one in-memory BUPT session; credentials are never retained as state."""

    def __init__(
        self,
        bootstrap_service: AuthBootstrapService | None = None,
        runtime_client_factory: Callable[[AppBusinessSession], BUPTClient] | None = None,
    ) -> None:
        self._client: BUPTClient | None = None
        self._lock = asyncio.Lock()
        self._bootstrap_service = bootstrap_service or AuthBootstrapService()
        self._runtime_client_factory = runtime_client_factory or create_runtime_client

    def get_client(self) -> BUPTClient | None:
        """Return the current client reference; routes should use ``acquire_client`` instead."""
        return self._client

    async def login(self, username: str, password: str) -> ApiResponse[SessionStatus]:
        """Bootstrap CAS briefly, then retain only a new app-only runtime client."""
        async with self._lock:
            await self._clear_locked()
            try:
                bootstrap = await self._bootstrap_service.authenticate(username, password)
                client = self._runtime_client_factory(bootstrap.session)
            except AuthFailure as exc:
                return ApiResponse.error(_login_error_code(exc), "authentication failed")
            except Exception:
                return ApiResponse.error(ErrorCode.INTERNAL_ERROR, "authentication could not be completed")
            self._client = client
            return ApiResponse.ok(_authenticated_status(), "Authentication successful")

    async def logout(self) -> ApiResponse[SessionStatus]:
        """Close only this program's client; it never logs out browser-wide BUPT SSO."""
        async with self._lock:
            await self._clear_locked()
            return ApiResponse.ok(_unauthenticated_status(), "Logged out")

    async def status(self) -> ApiResponse[SessionStatus]:
        async with self._lock:
            if self._client is None:
                return ApiResponse.ok(_unauthenticated_status())
            verification = await self._client.check_auth_result()
            if verification.success:
                return ApiResponse.ok(_authenticated_status())
            if verification.code == ErrorCode.SESSION_EXPIRED:
                await self._clear_locked()
                return ApiResponse.ok(_expired_status(), "session expired; please log in again")
            return ApiResponse.error(verification.code, "session status could not be checked")

    @asynccontextmanager
    async def acquire_client(self) -> AsyncIterator[BUPTClient]:
        """Lease the authenticated client while preventing concurrent logout/login closure."""
        async with self._lock:
            if self._client is None:
                raise SessionAccessError(ErrorCode.AUTH_REQUIRED, "log in before accessing electricity data")
            verification = await self._client.check_auth_result()
            if not verification.success:
                if verification.code == ErrorCode.SESSION_EXPIRED:
                    await self._clear_locked()
                    raise SessionAccessError(ErrorCode.SESSION_EXPIRED, "session expired; please log in again")
                raise SessionAccessError(verification.code, "session could not be checked")
            yield self._client

    async def _clear_locked(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.close()


def _authenticated_status() -> SessionStatus:
    return SessionStatus(authenticated=True, state=SessionState.AUTHENTICATED)


def _unauthenticated_status() -> SessionStatus:
    return SessionStatus(authenticated=False, state=SessionState.UNAUTHENTICATED)


def _expired_status() -> SessionStatus:
    return SessionStatus(authenticated=False, state=SessionState.SESSION_EXPIRED)


def _login_error_code(error: AuthFailure) -> ErrorCode:
    if error.kind == AuthErrorKind.TIMEOUT:
        return ErrorCode.TIMEOUT
    if error.kind == AuthErrorKind.NETWORK_ERROR:
        return ErrorCode.NETWORK_ERROR
    return ErrorCode.AUTH_FAILED
