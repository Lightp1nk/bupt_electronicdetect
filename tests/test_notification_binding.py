import asyncio
from datetime import datetime
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker,create_async_engine
from app.database.database import Base
from app.models import alert,collection,electricity,notification_binding,upstream_session,user
from app.repositories.notification_binding_repository import NotificationBindingRepository
from app.schemas.notification import NotificationBindingUpdate

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
