from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base, get_db_session
from app.main import app
from app.models.user import AppSession, User
from app.models.upstream_session import UpstreamSession
from app.providers.bupt_auth import AuthErrorKind, AuthFailure
from app.repositories.auth_repository import AuthRepository
from app.schemas.common import ApiResponse
from app.services.app_session_service import AppSessionConfig, SESSION_COOKIE_NAME, hash_token, utc_now
from app.services.auth_bootstrap import AppBusinessCookie, AppBusinessSession, BootstrapResult
from app.services.auth_session import AuthSessionManager
from app.services.upstream_session_service import UpstreamSessionService


class FakeRuntimeClient:
    def __init__(self) -> None:
        self.closed = 0

    async def check_auth_result(self) -> ApiResponse[bool]:
        return ApiResponse.ok(True)

    async def get_buildings(self, *, area_id: str) -> ApiResponse[list[object]]:
        return ApiResponse.ok([])

    async def close(self) -> None:
        self.closed += 1


class FakeBootstrapService:
    async def authenticate(self, username: str, password: str) -> BootstrapResult:
        if username == "failed":
            raise AuthFailure(AuthErrorKind.APP_SESSION_FAILED, "app callback")
        return BootstrapResult(
            username=username,
            session=AppBusinessSession(
                (
                    AppBusinessCookie("eai-sess", "test-session", "app.bupt.edu.cn", "/", None, True),
                    AppBusinessCookie("UUkey", "test-key", "app.bupt.edu.cn", "/", None, False),
                )
            ),
        )


def test_app_sessions_identify_browsers_without_creating_runtime_mapping(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'auth.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_session():
            async with sessions() as session:
                yield session

        runtimes: list[FakeRuntimeClient] = []

        def runtime_factory(_: AppBusinessSession) -> FakeRuntimeClient:
            runtime = FakeRuntimeClient()
            runtimes.append(runtime)
            return runtime

        app.dependency_overrides[get_db_session] = override_session
        app.state.app_session_config = AppSessionConfig(ttl=timedelta(days=14), secure_cookie=False, last_seen_interval=timedelta())
        app.state.upstream_session_service = UpstreamSessionService(sessions)
        app.state.auth_session_manager = AuthSessionManager(
            FakeBootstrapService(), runtime_factory,
            runtime_session_loader=app.state.upstream_session_service.load_business_session,
        )  # type: ignore[arg-type]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as browser_a, httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as browser_b:
            missing = await browser_a.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            login_a = await browser_a.post("/api/v1/auth/login", json={"username": "user-a", "password": "not-real"})
            login_a_again = await browser_a.post("/api/v1/auth/login", json={"username": "user-a", "password": "not-real"})
            login_b = await browser_b.post("/api/v1/auth/login", json={"username": "user-b", "password": "not-real"})
            status_a = await browser_a.get("/api/v1/auth/status")
            status_b = await browser_b.get("/api/v1/auth/status")
            a_buildings = await browser_a.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            b_buildings = await browser_b.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            token_a = browser_a.cookies.get(SESSION_COOKIE_NAME)
            token_b = browser_b.cookies.get(SESSION_COOKIE_NAME)
            logout_a = await browser_a.post("/api/v1/auth/logout")
            a_after_logout = await browser_a.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            b_after_a_logout = await browser_b.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            raw_a = browser_a.cookies.get(SESSION_COOKIE_NAME)
            raw_b = browser_b.cookies.get(SESSION_COOKIE_NAME)

        assert missing.status_code == 401
        assert login_a.json()["data"]["user"]["bupt_username"] == "user-a"
        assert login_a_again.json()["success"] is True
        assert login_b.json()["data"]["user"]["bupt_username"] == "user-b"
        assert status_a.json()["data"]["user"]["bupt_username"] == "user-a"
        assert status_b.json()["data"]["user"]["bupt_username"] == "user-b"
        assert a_buildings.status_code == b_buildings.status_code == 200
        assert logout_a.json()["success"] is True
        assert a_after_logout.status_code == 401
        assert b_after_a_logout.status_code == 200
        assert "httponly" in login_a.headers["set-cookie"].lower()
        assert "samesite=lax" in login_a.headers["set-cookie"].lower()
        assert token_a is not None and token_b is not None and token_a != token_b
        assert raw_a is None  # Logout clears the browser's raw token.
        assert raw_b is not None

        # The browser sessions are separate, while the runtime remains one global Phase-A client.
        assert app.state.auth_session_manager.get_client() is runtimes[-1]
        assert runtimes[-1].closed == 0
        assert all(runtime.closed == 1 for runtime in runtimes[:-1])

        async with sessions() as session:
            users = list((await session.scalars(select(User).order_by(User.bupt_username))).all())
            app_sessions = list((await session.scalars(select(AppSession))).all())
            upstream_sessions = list((await session.scalars(select(UpstreamSession).order_by(UpstreamSession.user_id))).all())
        assert [user.bupt_username for user in users] == ["user-a", "user-b"]
        assert len(app_sessions) == 3
        assert len({record.token_hash for record in app_sessions}) == 3
        assert all(len(record.token_hash) == 64 for record in app_sessions)
        assert token_a not in {record.token_hash for record in app_sessions}
        assert token_b not in {record.token_hash for record in app_sessions}
        assert sum(record.revoked_at is not None for record in app_sessions if record.user_id == users[0].id) == 1
        assert all(record.revoked_at is None for record in app_sessions if record.user_id == users[1].id)
        assert len(upstream_sessions) == 2
        assert all(record.status == "ACTIVE" for record in upstream_sessions)
        assert all("test-session" not in record.encrypted_cookie_blob for record in upstream_sessions)
        assert all("test-key" not in record.encrypted_cookie_blob for record in upstream_sessions)

        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(scenario())


def test_expired_revoked_and_failed_authentication_do_not_authenticate_or_create_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'expired.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_session():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_db_session] = override_session
        app.state.app_session_config = AppSessionConfig(last_seen_interval=timedelta())
        app.state.upstream_session_service = UpstreamSessionService(sessions)
        app.state.auth_session_manager = AuthSessionManager(
            FakeBootstrapService(), lambda _: FakeRuntimeClient(),
            runtime_session_loader=app.state.upstream_session_service.load_business_session,
        )  # type: ignore[arg-type]
        now = utc_now()
        expired_raw, revoked_raw = "expired-test-token", "revoked-test-token"
        async with sessions() as session:
            repository = AuthRepository(session)
            user = await repository.get_or_create_authenticated_user("existing", now)
            await repository.create_app_session(user_id=user.id, token_hash=hash_token(expired_raw), now=now, expires_at=now - timedelta(seconds=1))
            await repository.create_app_session(user_id=user.id, token_hash=hash_token(revoked_raw), now=now, expires_at=now + timedelta(days=1))
            await repository.revoke_by_token_hash(hash_token(revoked_raw), now=now)
            await session.commit()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as browser:
            browser.cookies.set(SESSION_COOKIE_NAME, expired_raw)
            expired = await browser.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            browser.cookies.set(SESSION_COOKIE_NAME, revoked_raw)
            revoked = await browser.get("/api/v1/electricity/buildings", params={"area_id": "1"})
            failed = await browser.post("/api/v1/auth/login", json={"username": "failed", "password": "not-real"})

        assert expired.status_code == revoked.status_code == 401
        assert failed.status_code == 401
        async with sessions() as session:
            assert await session.scalar(select(User).where(User.bupt_username == "failed")) is None
            assert await session.scalar(select(UpstreamSession).join(User).where(User.bupt_username == "failed")) is None
        app.dependency_overrides.clear()
        await engine.dispose()

    asyncio.run(scenario())
