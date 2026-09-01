"""User-scoped in-memory lifecycle management for app-only BUPT runtime clients."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable

from app.providers.bupt_auth import AuthErrorKind, AuthFailure
from app.providers.bupt_client import BUPTClient
from app.schemas.common import ApiResponse, ErrorCode
from app.services.auth_bootstrap import AppBusinessSession, AuthBootstrapService, BootstrapResult, create_runtime_client
from app.services.upstream_session_service import (
    UpstreamSessionConfigurationError,
    UpstreamSessionError,
    UpstreamSessionStatus,
)


@dataclass(frozen=True)
class SessionAccessError(Exception):
    code: ErrorCode
    message: str


class RuntimeSessionManager:
    """Own reusable app-only clients, isolated by local application user id.

    The scheduler has no user scope until Phase D. Its compatibility path stores
    only a last-login *user id*, never a global BUPT client.
    """

    def __init__(
        self,
        bootstrap_service: AuthBootstrapService | None = None,
        runtime_client_factory: Callable[[AppBusinessSession], BUPTClient] | None = None,
        runtime_session_loader: Callable[[int], Awaitable[AppBusinessSession]] | None = None,
        runtime_cookie_persister: Callable[[int, BUPTClient], Awaitable[bool]] | None = None,
        runtime_marker: Callable[[int], Awaitable[None]] | None = None,
        runtime_expiry_marker: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        self._clients: dict[int, BUPTClient] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._scheduler_user_id: int | None = None  # TODO(Phase D): per-user collection scheduling.
        self._bootstrap_service = bootstrap_service or AuthBootstrapService()
        self._runtime_client_factory = runtime_client_factory or create_runtime_client
        self._runtime_session_loader = runtime_session_loader
        self._runtime_cookie_persister = runtime_cookie_persister
        self._runtime_marker = runtime_marker
        self._runtime_expiry_marker = runtime_expiry_marker

    async def bootstrap_login(self, username: str, password: str) -> ApiResponse[BootstrapResult]:
        """Authenticate upstream without retaining credentials in application state."""
        try:
            return ApiResponse.ok(await self._bootstrap_service.authenticate(username, password))
        except AuthFailure as exc:
            return ApiResponse.error(_login_error_code(exc), "authentication failed")
        except Exception:
            return ApiResponse.error(ErrorCode.INTERNAL_ERROR, "authentication could not be completed")

    async def register_client(self, user_id: int, app_session: AppBusinessSession) -> ApiResponse[None]:
        """Register a fresh post-bootstrap runtime for exactly one user."""
        lock = await self._user_lock(user_id)
        async with lock:
            try:
                client = self._runtime_client_factory(app_session)
            except Exception:
                return ApiResponse.error(ErrorCode.INTERNAL_ERROR, "runtime client could not be created")
            await self._remove_locked(user_id)
            self._clients[user_id] = client
            self._scheduler_user_id = user_id
            return ApiResponse.ok(None, "runtime client registered")

    async def get_client(self, user_id: int) -> BUPTClient:
        """Return this user's cached client or restore it once from encrypted storage."""
        lock = await self._user_lock(user_id)
        async with lock:
            return await self._get_or_create_locked(user_id)

    async def invalidate_client(self, user_id: int) -> None:
        """Discard only one user's runtime after the upstream session expires."""
        lock = await self._user_lock(user_id)
        async with lock:
            await self._invalidate_locked(user_id)

    async def remove_client(self, user_id: int) -> None:
        """Close and forget only one user's in-memory runtime client."""
        lock = await self._user_lock(user_id)
        async with lock:
            await self._remove_locked(user_id)
            if self._scheduler_user_id == user_id:
                self._scheduler_user_id = None

    async def close_all(self) -> None:
        """Application-shutdown-only cleanup for every managed runtime client."""
        clients, self._clients = list(self._clients.values()), {}
        self._scheduler_user_id = None
        await asyncio.gather(*(client.close() for client in clients))

    def has_scheduler_client(self) -> bool:
        """Temporary Phase-D compatibility status check without exposing a Client."""
        return self._scheduler_user_id is not None and self._scheduler_user_id in self._clients

    def has_client(self, user_id: int) -> bool:
        """Report whether this user's Runtime Client is currently live in this process."""
        return user_id in self._clients

    @asynccontextmanager
    async def acquire_client(self, user_id: int | None = None) -> AsyncIterator[BUPTClient]:
        """Lease one user runtime exclusively while it performs an upstream request."""
        resolved_user_id = user_id if user_id is not None else self._scheduler_user_id
        if resolved_user_id is None:
            raise SessionAccessError(ErrorCode.AUTH_REQUIRED, "log in before accessing electricity data")
        lock = await self._user_lock(resolved_user_id)
        async with lock:
            client = await self._get_or_create_locked(resolved_user_id)
            verification = await client.check_auth_result()
            if not verification.success:
                if verification.code == ErrorCode.SESSION_EXPIRED:
                    await self._invalidate_locked(resolved_user_id)
                    raise SessionAccessError(ErrorCode.SESSION_EXPIRED, "session expired; please log in again")
                raise SessionAccessError(verification.code, "session could not be checked")
            await self._mark_validated(resolved_user_id)
            try:
                yield client
            finally:
                post_verification = await client.check_auth_result()
                if post_verification.success:
                    await self._mark_validated(resolved_user_id)
                    await self._persist_runtime_cookies(resolved_user_id, client)
                elif post_verification.code == ErrorCode.SESSION_EXPIRED:
                    await self._invalidate_locked(resolved_user_id)

    async def _user_lock(self, user_id: int) -> asyncio.Lock:
        # This contains no await, so one event-loop turn creates each lock atomically.
        return self._locks.setdefault(user_id, asyncio.Lock())

    async def _get_or_create_locked(self, user_id: int) -> BUPTClient:
        cached = self._clients.get(user_id)
        if cached is not None:
            return cached
        if self._runtime_session_loader is None:
            raise SessionAccessError(ErrorCode.REAUTH_REQUIRED, "upstream session restoration is unavailable")
        try:
            app_session = await self._runtime_session_loader(user_id)
            client = self._runtime_client_factory(app_session)
        except UpstreamSessionConfigurationError as exc:
            raise SessionAccessError(ErrorCode.INTERNAL_ERROR, "upstream session encryption is not configured") from exc
        except UpstreamSessionError as exc:
            code = ErrorCode.REAUTH_REQUIRED if exc.status == UpstreamSessionStatus.REAUTH_REQUIRED else ErrorCode.SESSION_EXPIRED
            raise SessionAccessError(code, "upstream session requires reauthentication") from exc
        except Exception as exc:
            raise SessionAccessError(ErrorCode.INTERNAL_ERROR, "runtime client could not be restored") from exc
        self._clients[user_id] = client
        return client

    async def _invalidate_locked(self, user_id: int) -> None:
        await self._remove_locked(user_id)
        if self._scheduler_user_id == user_id:
            self._scheduler_user_id = None
        if self._runtime_expiry_marker is not None:
            await self._runtime_expiry_marker(user_id)

    async def _remove_locked(self, user_id: int) -> None:
        client = self._clients.pop(user_id, None)
        if client is not None:
            await client.close()

    async def _persist_runtime_cookies(self, user_id: int, client: BUPTClient) -> None:
        if self._runtime_cookie_persister is None:
            return
        try:
            await self._runtime_cookie_persister(user_id, client)
        except UpstreamSessionError as exc:
            if exc.status == UpstreamSessionStatus.EXPIRED:
                await self._invalidate_locked(user_id)
        except UpstreamSessionConfigurationError:
            # The completed request remains valid; a future restore requires reauthentication.
            return

    async def _mark_validated(self, user_id: int) -> None:
        if self._runtime_marker is not None:
            await self._runtime_marker(user_id)


# Kept as a source-compatible name while callers migrate to RuntimeSessionManager.
AuthSessionManager = RuntimeSessionManager


def _login_error_code(error: AuthFailure) -> ErrorCode:
    if error.kind == AuthErrorKind.TIMEOUT:
        return ErrorCode.TIMEOUT
    if error.kind == AuthErrorKind.NETWORK_ERROR:
        return ErrorCode.NETWORK_ERROR
    return ErrorCode.AUTH_FAILED
