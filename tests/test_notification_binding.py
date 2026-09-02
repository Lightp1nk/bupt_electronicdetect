import asyncio
import os
from datetime import datetime
import pytest
import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker,create_async_engine
from app.database.database import Base
from app.models import alert,collection,electricity,notification_binding,upstream_session,user
from app.repositories.notification_binding_repository import NotificationBindingRepository
from app.schemas.notification import NotificationBindingUpdate
from app.database.database import get_db_session
from app.main import app

def test_notification_bindings_are_user_scoped_and_upserted(tmp_path):
 async def run():
  e=create_async_engine(f"sqlite+aiosqlite:///{(tmp_path/'n.db').as_posix()}")
  async with e.begin() as c: await c.run_sync(Base.metadata.create_all)
  S=async_sessionmaker(e,expire_on_commit=False,class_=AsyncSession); now=datetime.now()
  async with S() as s:
   r=NotificationBindingRepository(s); await r.upsert(1,'astrbot','qq','123456',True,now); await r.upsert(2,'astrbot','qq','654321',True,now); await r.upsert(1,'astrbot','qq','111111',False,now); await s.commit()
   assert len(await r.list(1))==1 and (await r.list(1))[0].target_id=='111111'; assert (await r.list(2))[0].target_id=='654321'
   await r.delete(1,'astrbot','qq');await s.commit();assert not await r.list(1) and len(await r.list(2))==1
  await e.dispose()
 asyncio.run(run())

def test_notification_binding_validates_qq_and_provider_platform():
 assert NotificationBindingUpdate(provider='astrbot',platform='qq',target_id='12345',enabled=True).target_id=='12345'
 for value in ({'provider':'unknown','platform':'qq','target_id':'12345','enabled':True},{'provider':'astrbot','platform':'unknown','target_id':'12345','enabled':True},{'provider':'astrbot','platform':'qq','target_id':'abc','enabled':True}):
  with pytest.raises(ValidationError): NotificationBindingUpdate(**value)


def test_bridge_can_only_bind_an_explicitly_enabled_qq_target(tmp_path):
 async def run():
  e=create_async_engine(f"sqlite+aiosqlite:///{(tmp_path/'bridge.db').as_posix()}")
  async with e.begin() as c: await c.run_sync(Base.metadata.create_all)
  S=async_sessionmaker(e,expire_on_commit=False,class_=AsyncSession)
  async def override_session():
   async with S() as session: yield session
  previous = os.environ.get('ASTRBOT_BRIDGE_TOKEN')
  os.environ['ASTRBOT_BRIDGE_TOKEN'] = 'test-bridge-token'
  app.dependency_overrides[get_db_session] = override_session
  try:
   transport=httpx.ASGITransport(app=app)
   async with httpx.AsyncClient(transport=transport,base_url='http://test') as client:
    assert (await client.get('/api/v1/notification/bridge/bindings/123456')).status_code == 401
    headers={'Authorization':'Bearer test-bridge-token'}
    missing=await client.get('/api/v1/notification/bridge/bindings/123456',headers=headers)
    assert missing.status_code == 200 and missing.json()['data']['eligible'] is False
    async with S() as session:
     await NotificationBindingRepository(session).upsert(1,'astrbot','qq','123456',True,datetime.now()); await session.commit()
    enabled=await client.get('/api/v1/notification/bridge/bindings/123456',headers=headers)
    assert enabled.json()['data']['eligible'] is True
    async with S() as session:
     await NotificationBindingRepository(session).upsert(1,'astrbot','qq','123456',False,datetime.now()); await session.commit()
    disabled=await client.get('/api/v1/notification/bridge/bindings/123456',headers=headers)
    assert disabled.json()['data']['eligible'] is False
  finally:
   app.dependency_overrides.clear()
   if previous is None: os.environ.pop('ASTRBOT_BRIDGE_TOKEN',None)
   else: os.environ['ASTRBOT_BRIDGE_TOKEN'] = previous
   await e.dispose()
 asyncio.run(run())
