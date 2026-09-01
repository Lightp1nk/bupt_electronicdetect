"""Dependencies that resolve a user's isolated upstream runtime client."""

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError
from app.database.database import get_db_session
from app.models.user import User
from app.providers.bupt_client import BUPTClient
from app.repositories.auth_repository import AuthRepository
from app.schemas.common import ErrorCode
from app.services.app_session_service import AppSessionConfig, SESSION_COOKIE_NAME, hash_token, utc_now
from app.services.auth_session import SessionAccessError


async def get_current_user(
    request: Request, session: AsyncSession = Depends(get_db_session),
) -> User:
    """Resolve the local browser identity; it is intentionally independent of BUPT Runtime state."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        raise ApiError(ErrorCode.AUTH_REQUIRED, "sign in before accessing this resource")
    config: AppSessionConfig = request.app.state.app_session_config
    user = await AuthRepository(session).get_active_user_by_token_hash(
        hash_token(raw_token), now=utc_now(), last_seen_interval=config.last_seen_interval,
    )
    if user is None:
        raise ApiError(ErrorCode.AUTH_REQUIRED, "application session is invalid or expired")
    await session.commit()
    return user


async def get_authenticated_bupt_client(
    request: Request, current_user: User = Depends(get_current_user),
) -> AsyncIterator[BUPTClient]:
    """Current user selects and exclusively leases their reusable Runtime Client."""
    manager = request.app.state.auth_session_manager
    try:
        async with manager.acquire_client(current_user.id) as client:
            yield client
    except SessionAccessError as exc:
        raise ApiError(exc.code, exc.message) from exc
