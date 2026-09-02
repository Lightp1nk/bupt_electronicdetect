import asyncio
from datetime import datetime
import httpx
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker,create_async_engine
from app.database.database import Base
from app.api.dependencies import get_current_user
from app.models import alert,chat_identity,collection,electricity,notification_binding,upstream_session,user
from app.models.chat_identity import ChatIdentity
from app.models.user import User
from app.repositories.notification_binding_repository import NotificationBindingRepository
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

def test_notification_target_is_derived_from_chat_identity_and_only_enabled_is_mutable(tmp_path):
 async def run():
  e=create_async_engine(f"sqlite+aiosqlite:///{(tmp_path/'bridge.db').as_posix()}")
  async with e.begin() as c: await c.run_sync(Base.metadata.create_all)
  S=async_sessionmaker(e,expire_on_commit=False,class_=AsyncSession)
  async def override_session():
   async with S() as session: yield session
  app.dependency_overrides[get_db_session] = override_session
  app.dependency_overrides[get_current_user] = lambda: type('UserContext', (), {'id': 1})()
  try:
   now=datetime.now()
   async with S() as session:
    session.add(User(id=1,bupt_username='a',display_name=None,created_at=now,last_login_at=now)); await session.commit()
   transport=httpx.ASGITransport(app=app)
   async with httpx.AsyncClient(transport=transport,base_url='http://test') as client:
    # The legacy endpoint no longer accepts a hand-entered target_id.
    assert (await client.put('/api/v1/notification/bindings',json={'provider':'astrbot','platform':'qq','target_id':'123456','enabled':True})).status_code == 405
    assert (await client.put('/api/v1/notification/bindings/astrbot/qq/enabled',json={'enabled':True})).status_code == 404
    async with S() as session:
     session.add(ChatIdentity(user_id=1,platform='qq',external_id='123456',verified_at=now,created_at=now,updated_at=now)); await session.commit()
    enabled=await client.put('/api/v1/notification/bindings/astrbot/qq/enabled',json={'enabled':True})
    assert enabled.status_code == 200 and enabled.json()['data']['target_id'] == '123456' and enabled.json()['data']['enabled'] is True
    disabled=await client.put('/api/v1/notification/bindings/astrbot/qq/enabled',json={'enabled':False})
    assert disabled.status_code == 200 and disabled.json()['data']['target_id'] == '123456' and disabled.json()['data']['enabled'] is False
    async with S() as session:
     bindings=await NotificationBindingRepository(session).list(1); assert len(bindings)==1 and bindings[0].target_id=='123456'
  finally:
   app.dependency_overrides.clear()
   await e.dispose()
 asyncio.run(run())
