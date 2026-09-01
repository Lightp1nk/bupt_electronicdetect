from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base
from app.models.upstream_session import UpstreamSession
from app.providers.bupt_client import BUPTClient
from app.repositories.auth_repository import AuthRepository
from app.repositories.upstream_session_repository import UpstreamSessionRepository
from app.services.app_session_service import utc_now
from app.services.auth_bootstrap import AppBusinessCookie, AppBusinessSession, create_runtime_client
from app.services.auth_session import AuthSessionManager, SessionAccessError
from app.services.upstream_session_service import (
    UpstreamSessionConfigurationError,
    UpstreamSessionCipher,
    UpstreamSessionError,
    UpstreamSessionService,
    UpstreamSessionStatus,
)


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def app_session(value: str) -> AppBusinessSession:
    return AppBusinessSession(
        (
            AppBusinessCookie("eai-sess", f"session-{value}", "app.bupt.edu.cn", "/", None, True),
            AppBusinessCookie("UUkey", f"key-{value}", ".app.bupt.edu.cn", "/", None, False),
        )
    )


async def make_services(path: Path) -> tuple[object, async_sessionmaker[AsyncSession], UpstreamSessionService]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return engine, sessions, UpstreamSessionService(sessions)


async def create_user_and_session(
    sessions: async_sessionmaker[AsyncSession], service: UpstreamSessionService, username: str, value: str,
) -> int:
    now = utc_now()
    async with sessions() as session:
        user = await AuthRepository(session).get_or_create_authenticated_user(username, now)
        await service.save_authenticated_session(session, user_id=user.id, app_session=app_session(value), now=now)
        await session.commit()
        return user.id


def test_upstream_sessions_are_per_user_encrypted_and_runtime_restorable(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, sessions, service = await make_services(tmp_path / "upstream.db")
        user_a = await create_user_and_session(sessions, service, "user-a", "a")
        user_b = await create_user_and_session(sessions, service, "user-b", "b")
        async with sessions() as session:
            records = [await UpstreamSessionRepository(session).get_by_user_id(user_a), await UpstreamSessionRepository(session).get_by_user_id(user_b)]
        assert all(record is not None and record.status == UpstreamSessionStatus.ACTIVE for record in records)
        assert records[0].encrypted_cookie_blob != records[1].encrypted_cookie_blob  # Fernet is randomized.
        assert "session-a" not in records[0].encrypted_cookie_blob
        assert "key-a" not in records[0].encrypted_cookie_blob
        assert "eai-sess" not in records[0].encrypted_cookie_blob
        assert "UUkey" not in records[0].encrypted_cookie_blob

        restored = await service.load_business_session(user_a)
        runtime = create_runtime_client(restored, client_factory=lambda: BUPTClient(transport=httpx.MockTransport(lambda _: httpx.Response(200))))
        try:
            assert {cookie.name for cookie in runtime.client.cookies.jar} == {"eai-sess", "UUkey"}
            assert {cookie.domain.lstrip(".") for cookie in runtime.client.cookies.jar} == {"app.bupt.edu.cn"}
            assert all(cookie.domain.lstrip(".") != "auth.bupt.edu.cn" for cookie in runtime.client.cookies.jar)
        finally:
            await runtime.close()
        await engine.dispose()

    run(scenario())


def test_missing_or_invalid_fernet_key_never_falls_back_to_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_UPSTREAM_SESSION_KEY")
    with pytest.raises(UpstreamSessionConfigurationError):
        UpstreamSessionCipher.from_environment()
    monkeypatch.setenv("APP_UPSTREAM_SESSION_KEY", "not-a-valid-key")
    with pytest.raises(UpstreamSessionConfigurationError):
        UpstreamSessionCipher.from_environment()


def test_missing_and_undecryptable_upstream_sessions_require_reauthentication(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, sessions, service = await make_services(tmp_path / "invalid.db")
        with pytest.raises(UpstreamSessionError) as missing:
            await service.load_business_session(404)
        assert missing.value.status == UpstreamSessionStatus.REAUTH_REQUIRED

        user_id = await create_user_and_session(sessions, service, "user-a", "a")
        async with sessions() as session:
            record = await UpstreamSessionRepository(session).get_by_user_id(user_id)
            assert record is not None
            record.encrypted_cookie_blob = "not-a-fernet-token"
            await session.commit()
        with pytest.raises(UpstreamSessionError) as invalid:
            await service.load_business_session(user_id)
        assert invalid.value.status == UpstreamSessionStatus.EXPIRED
        async with sessions() as session:
            record = await UpstreamSessionRepository(session).get_by_user_id(user_id)
            assert record is not None and record.status == UpstreamSessionStatus.EXPIRED
        await engine.dispose()

    run(scenario())


def test_runtime_cookie_rotation_is_reencrypted_and_manager_reuses_by_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, sessions, service = await make_services(tmp_path / "rotation.db")
        user_a = await create_user_and_session(sessions, service, "user-a", "a")
        user_b = await create_user_and_session(sessions, service, "user-b", "b")

        clients: list[object] = []

        def factory(session: AppBusinessSession):
            client = create_runtime_client(session)
            clients.append(client)
            return client

        manager = AuthSessionManager(
            runtime_client_factory=factory,
            runtime_session_loader=service.load_business_session,
            runtime_cookie_persister=service.persist_runtime_cookies,
            runtime_marker=service.mark_validated,
            runtime_expiry_marker=service.mark_reauth_required,
        )
        client_a = await manager.get_client(user_a)
        assert client_a is await manager.get_client(user_a)
        for cookie in client_a.client.cookies.jar:
            if cookie.name == "eai-sess":
                cookie.value = "session-a-rotated"
        assert await service.persist_runtime_cookies(user_a, client_a) is True
        assert (await service.load_business_session(user_a)).cookies[0].value == "session-a-rotated"
        client_b = await manager.get_client(user_b)
        assert client_b is not client_a
        assert not client_a.client.is_closed
        assert len(clients) == 2
        await manager.close_all()
        await engine.dispose()

    run(scenario())
