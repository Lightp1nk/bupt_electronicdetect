"""Dependencies that lease the one authenticated upstream client."""

from collections.abc import AsyncIterator

from fastapi import Request

from app.api.errors import ApiError
from app.providers.bupt_client import BUPTClient
from app.services.auth_session import SessionAccessError


async def get_authenticated_bupt_client(request: Request) -> AsyncIterator[BUPTClient]:
    manager = request.app.state.auth_session_manager
    try:
        async with manager.acquire_client() as client:
            yield client
    except SessionAccessError as exc:
        raise ApiError(exc.code, exc.message) from exc
