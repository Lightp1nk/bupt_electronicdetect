from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification_binding import NotificationBinding

class NotificationBindingRepository:
    def __init__(self, session: AsyncSession): self._session=session
    async def list(self,user_id:int): return list((await self._session.scalars(select(NotificationBinding).where(NotificationBinding.user_id==user_id))).all())
    async def has_enabled_target(self, provider: str, platform: str, target_id: str) -> bool:
        """Return whether a target is explicitly enabled by any local user."""
        value = await self._session.scalar(
            select(NotificationBinding.id).where(
                NotificationBinding.provider == provider,
                NotificationBinding.platform == platform,
                NotificationBinding.target_id == target_id,
                NotificationBinding.enabled.is_(True),
            ).limit(1)
        )
        return value is not None
    async def upsert(self,user_id:int,provider:str,platform:str,target_id:str,enabled:bool,now:datetime):
        value=await self._session.scalar(select(NotificationBinding).where(NotificationBinding.user_id==user_id,NotificationBinding.provider==provider,NotificationBinding.platform==platform))
        if value is None: value=NotificationBinding(user_id=user_id,provider=provider,platform=platform,target_id=target_id,enabled=enabled,created_at=now,updated_at=now);self._session.add(value)
        else: value.target_id,value.enabled,value.updated_at=target_id,enabled,now
        await self._session.flush();return value
    async def delete(self,user_id:int,provider:str,platform:str):
        value=await self._session.scalar(select(NotificationBinding).where(NotificationBinding.user_id==user_id,NotificationBinding.provider==provider,NotificationBinding.platform==platform))
        if value: await self._session.delete(value)
