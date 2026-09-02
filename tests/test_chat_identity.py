import asyncio
import os
from datetime import timedelta
from pathlib import Path
import sqlite3
import sys

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_current_user
from app.database.database import Base, get_db_session
from app.main import app
from app.models import chat_identity, user  # noqa: F401 -- register metadata
from app.models.chat_identity import ChatIdentity, PendingChatBinding
from app.models.user import User
from app.services.app_session_service import utc_now


def test_chat_identity_binding_flow_is_scoped_and_does_not_store_plain_code(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'chat.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_session():
            async with sessions() as session:
                yield session

        current = {"id": 1}
        app.dependency_overrides[get_db_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: type("UserContext", (), {"id": current["id"]})()
        previous = os.environ.get("ASTRBOT_INTERNAL_TOKEN")
        os.environ["ASTRBOT_INTERNAL_TOKEN"] = "internal-test-token"
        now = utc_now()
        try:
            async with sessions() as session:
                session.add_all([
                    User(bupt_username="a", display_name=None, created_at=now, last_login_at=now),
                    User(bupt_username="b", display_name=None, created_at=now, last_login_at=now),
                ])
                await session.commit()

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                generated = await client.post("/api/v1/chat/identity/binding-code?platform=qq")
                assert generated.status_code == 200
                code = generated.json()["data"]["code"]
                assert "-" in code
                assert (await client.post("/api/internal/chat/bind", json={"platform": "qq", "external_id": "123456", "code": code})).status_code == 401
                assert (await client.post("/api/internal/chat/bind", headers={"Authorization": "Bearer wrong"}, json={"platform": "qq", "external_id": "123456", "code": code})).status_code == 401
                success = await client.post("/api/internal/chat/bind", headers={"Authorization": "Bearer internal-test-token"}, json={"platform": "qq", "external_id": "123456", "code": code})
                assert success.status_code == 200 and success.json()["data"]["external_id"] == "123456"
                assert (await client.post("/api/internal/chat/bind", headers={"Authorization": "Bearer internal-test-token"}, json={"platform": "qq", "external_id": "123456", "code": code})).status_code == 401
                assert (await client.post("/api/internal/chat/bind", headers={"Authorization": "Bearer internal-test-token"}, json={"platform": "qq", "external_id": "123456", "code": "WRONG-CODE", "user_id": 99})).status_code == 422

                current["id"] = 2
                b_code = (await client.post("/api/v1/chat/identity/binding-code?platform=qq")).json()["data"]["code"]
                duplicate = await client.post("/api/internal/chat/bind", headers={"Authorization": "Bearer internal-test-token"}, json={"platform": "qq", "external_id": "123456", "code": b_code})
                assert duplicate.status_code == 409
                assert (await client.get("/api/v1/chat/identity?platform=qq")).json()["data"] is None

                current["id"] = 1
                new_code = (await client.post("/api/v1/chat/identity/binding-code?platform=qq")).json()["data"]["code"]
                rebound = await client.post("/api/internal/chat/bind", headers={"Authorization": "Bearer internal-test-token"}, json={"platform": "qq", "external_id": "654321", "code": new_code})
                assert rebound.status_code == 200
                assert (await client.get("/api/v1/chat/identity?platform=qq")).json()["data"]["external_id"] == "654321"

                current["id"] = 2
                assert (await client.delete("/api/v1/chat/identity/qq")).status_code == 404
                current["id"] = 1
                assert (await client.delete("/api/v1/chat/identity/qq")).status_code == 200

            async with sessions() as session:
                pending = (await session.scalars(select(PendingChatBinding))).all()
                identities = (await session.scalars(select(ChatIdentity))).all()
                assert all(code.replace("-", "") not in row.code_hash for row in pending)
                assert not identities
                assert all(not hasattr(row, "umo") for row in pending)
        finally:
            app.dependency_overrides.clear()
            if previous is None:
                os.environ.pop("ASTRBOT_INTERNAL_TOKEN", None)
            else:
                os.environ["ASTRBOT_INTERNAL_TOKEN"] = previous
            await engine.dispose()

    asyncio.run(scenario())


def test_expired_binding_code_is_rejected_and_marked_expired(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'expired.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_session():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_db_session] = override_session
        app.dependency_overrides[get_current_user] = lambda: type("UserContext", (), {"id": 1})()
        previous = os.environ.get("ASTRBOT_INTERNAL_TOKEN")
        os.environ["ASTRBOT_INTERNAL_TOKEN"] = "internal-test-token"
        now = utc_now()
        try:
            async with sessions() as session:
                session.add(User(bupt_username="a", display_name=None, created_at=now, last_login_at=now))
                await session.commit()
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                code = (await client.post("/api/v1/chat/identity/binding-code?platform=qq")).json()["data"]["code"]
                async with sessions() as session:
                    pending = await session.scalar(select(PendingChatBinding))
                    assert pending is not None
                    pending.expires_at = utc_now() - timedelta(seconds=1)
                    await session.commit()
                response = await client.post("/api/internal/chat/bind", headers={"Authorization": "Bearer internal-test-token"}, json={"platform": "qq", "external_id": "123456", "code": code})
                assert response.status_code == 401
                async with sessions() as session:
                    assert (await session.scalar(select(PendingChatBinding))).status == "expired"
        finally:
            app.dependency_overrides.clear()
            if previous is None:
                os.environ.pop("ASTRBOT_INTERNAL_TOKEN", None)
            else:
                os.environ["ASTRBOT_INTERNAL_TOKEN"] = previous
            await engine.dispose()

    asyncio.run(scenario())


def test_chat_identity_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")
    connection = sqlite3.connect(database_path)
    try:
        assert {"chat_identities", "pending_chat_bindings"}.issubset({row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")})
    finally:
        connection.close()
    command.downgrade(config, "20260901_05")
    connection = sqlite3.connect(database_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "chat_identities" not in tables and "pending_chat_bindings" not in tables
    finally:
        connection.close()
