import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.database import Base, get_db_session
from app.main import app
from app.models import chat_identity, collection, electricity, user  # noqa: F401 -- register metadata
from app.models.chat_identity import ChatIdentity
from app.models.collection import CollectionSettings
from app.models.electricity import ElectricityRecord
from app.models.user import User
from app.services.app_session_service import utc_now


def test_internal_chat_summary_is_authenticated_user_scoped_and_read_only(tmp_path) -> None:
    async def scenario() -> None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'summary.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

        async def override_session():
            async with sessions() as session:
                yield session

        previous = os.environ.get("ASTRBOT_INTERNAL_TOKEN")
        os.environ["ASTRBOT_INTERNAL_TOKEN"] = "summary-test-token"
        app.dependency_overrides[get_db_session] = override_session
        now = utc_now()
        try:
            async with sessions() as session:
                session.add_all([
                    User(id=1, bupt_username="a", display_name=None, created_at=now, last_login_at=now),
                    User(id=2, bupt_username="b", display_name=None, created_at=now, last_login_at=now),
                    User(id=3, bupt_username="no-room", display_name=None, created_at=now, last_login_at=now),
                    User(id=4, bupt_username="no-data", display_name=None, created_at=now, last_login_at=now),
                    ChatIdentity(user_id=1, platform="qq", external_id="111111", verified_at=now, created_at=now, updated_at=now),
                    ChatIdentity(user_id=2, platform="qq", external_id="222222", verified_at=now, created_at=now, updated_at=now),
                    ChatIdentity(user_id=3, platform="qq", external_id="333333", verified_at=now, created_at=now, updated_at=now),
                    ChatIdentity(user_id=4, platform="qq", external_id="444444", verified_at=now, created_at=now, updated_at=now),
                    CollectionSettings(user_id=1, area_id="2", area_name="沙河", building_id="a", building_name="A楼", floor_id="1", floor_name="1层", room_id="101", room_name="101"),
                    CollectionSettings(user_id=2, area_id="2", area_name="沙河", building_id="b", building_name="B楼", floor_id="2", floor_name="2层", room_id="202", room_name="202"),
                    CollectionSettings(user_id=4, area_id="2", area_name="沙河", building_id="c", building_name="C楼", floor_id="3", floor_name="3层", room_id="303", room_name="303"),
                    ElectricityRecord(area_id="2", building_id="a", building_name="A楼", floor_id="1", floor_name="1层", room_id="101", room_name="101", remaining_money=47.14, remaining_kwh=12.5, remaining_energy_kwh=None, free_remaining_kwh=None, total_usage_kwh=5204.73, price_per_kwh=None, source_time=now - timedelta(days=1), query_time=now - timedelta(days=1), created_at=now - timedelta(days=1), raw_data_json={}),
                    ElectricityRecord(area_id="2", building_id="a", building_name="A楼", floor_id="1", floor_name="1层", room_id="101", room_name="101", remaining_money=46.0, remaining_kwh=10.0, remaining_energy_kwh=None, free_remaining_kwh=None, total_usage_kwh=5210.73, price_per_kwh=None, source_time=now, query_time=now, created_at=now, raw_data_json={}),
                    ElectricityRecord(area_id="2", building_id="b", building_name="B楼", floor_id="2", floor_name="2层", room_id="202", room_name="202", remaining_money=99.0, remaining_kwh=50.0, remaining_energy_kwh=None, free_remaining_kwh=None, total_usage_kwh=8000.0, price_per_kwh=None, source_time=now, query_time=now, created_at=now, raw_data_json={}),
                ])
                await session.commit()

            transport = httpx.ASGITransport(app=app)
            headers = {"Authorization": "Bearer summary-test-token"}
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                path = "/api/internal/chat/electricity/summary"
                assert (await client.post(path, json={"platform": "qq", "external_id": "111111"})).status_code == 401
                assert (await client.post(path, headers={"Authorization": "Bearer wrong"}, json={"platform": "qq", "external_id": "111111"})).status_code == 401
                a = await client.post(path, headers=headers, json={"platform": "qq", "external_id": "111111"})
                assert a.status_code == 200
                data = a.json()["data"]
                assert data["room_name"] == "沙河 · A楼 · 1层 · 101"
                assert data["balance"] == 46.0 and data["total_usage_kwh"] == 5210.73
                assert data["estimated_remaining_days"] is None
                assert {"user_id", "id", "room_id", "area_id", "cookie", "token"}.isdisjoint(data)
                b = await client.post(path, headers=headers, json={"platform": "qq", "external_id": "222222"})
                assert b.status_code == 200 and b.json()["data"]["balance"] == 99.0
                unbound = await client.post(path, headers=headers, json={"platform": "qq", "external_id": "999999"})
                assert unbound.status_code == 404 and unbound.json()["code"] == "CHAT_NOT_BOUND"
                no_room = await client.post(path, headers=headers, json={"platform": "qq", "external_id": "333333"})
                assert no_room.status_code == 404 and no_room.json()["code"] == "NO_ROOM_CONFIGURED"
                no_data = await client.post(path, headers=headers, json={"platform": "qq", "external_id": "444444"})
                assert no_data.status_code == 404 and no_data.json()["code"] == "NO_DATA"
                assert (await client.post(path, headers=headers, json={"platform": "qq", "external_id": "111111", "user_id": 2})).status_code == 422
        finally:
            app.dependency_overrides.clear()
            if previous is None:
                os.environ.pop("ASTRBOT_INTERNAL_TOKEN", None)
            else:
                os.environ["ASTRBOT_INTERNAL_TOKEN"] = previous
            await engine.dispose()

    asyncio.run(scenario())
