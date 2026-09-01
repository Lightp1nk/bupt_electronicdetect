"""Persistence operations for local users and hashed browser sessions."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AppSession, User


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_authenticated_user(self, bupt_username: str, now: datetime) -> User:
        user = await self._session.scalar(select(User).where(User.bupt_username == bupt_username))
        if user is None:
            user = User(bupt_username=bupt_username, created_at=now, last_login_at=now)
            self._session.add(user)
            await self._session.flush()
        else:
            user.last_login_at = now
        return user

    async def create_app_session(self, *, user_id: int, token_hash: str, now: datetime, expires_at: datetime) -> AppSession:
        app_session = AppSession(
            user_id=user_id,
            token_hash=token_hash,
            created_at=now,
            expires_at=expires_at,
            last_seen_at=now,
        )
        self._session.add(app_session)
        await self._session.flush()
        return app_session

    async def get_active_user_by_token_hash(
        self, token_hash: str, *, now: datetime, last_seen_interval: timedelta
    ) -> User | None:
        statement: Select[tuple[AppSession, User]] = (
            select(AppSession, User)
            .join(User, User.id == AppSession.user_id)
            .where(
                AppSession.token_hash == token_hash,
                AppSession.revoked_at.is_(None),
                AppSession.expires_at > now,
            )
        )
        row = (await self._session.execute(statement)).first()
        if row is None:
            return None
        app_session, user = row
        if now - app_session.last_seen_at >= last_seen_interval:
            app_session.last_seen_at = now
        return user

    async def revoke_by_token_hash(self, token_hash: str, *, now: datetime) -> bool:
        app_session = await self._session.scalar(select(AppSession).where(AppSession.token_hash == token_hash))
        if app_session is None or app_session.revoked_at is not None:
            return False
        app_session.revoked_at = now
        return True
