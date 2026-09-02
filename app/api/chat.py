"""Web and AstrBot-internal APIs for chat identity binding only."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _status_code
from app.api.dependencies import get_current_user
from app.database.database import get_db_session
from app.models.user import User
from app.schemas.chat import ChatBindingCodeRead, ChatIdentityRead, ChatPlatform, InternalChatBindRequest
from app.schemas.common import ApiResponse
from app.schemas.common import ErrorCode
from app.services.chat_identity_service import ChatIdentityService
from app.services.internal_auth import require_astrbot_internal


router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
internal_router = APIRouter(prefix="/api/internal/chat", tags=["chat-internal"])


def _chat_status_code(code: ErrorCode) -> int:
    return 409 if code == ErrorCode.BUSINESS_ERROR else _status_code(code)


@router.get("/identity", response_model=ApiResponse[ChatIdentityRead | None])
async def identity(platform: ChatPlatform, session: AsyncSession = Depends(get_db_session), user: User = Depends(get_current_user)) -> ApiResponse[ChatIdentityRead | None]:
    return await ChatIdentityService(session).get_identity(user.id, platform)


@router.post("/identity/binding-code", response_model=ApiResponse[ChatBindingCodeRead])
async def create_binding_code(platform: ChatPlatform, response: Response, session: AsyncSession = Depends(get_db_session), user: User = Depends(get_current_user)) -> ApiResponse[ChatBindingCodeRead]:
    result = await ChatIdentityService(session).create_binding_code(user.id, platform)
    response.status_code = _chat_status_code(result.code)
    return result


@router.delete("/identity/{platform}", response_model=ApiResponse[None])
async def delete_identity(platform: ChatPlatform, response: Response, session: AsyncSession = Depends(get_db_session), user: User = Depends(get_current_user)) -> ApiResponse[None]:
    result = await ChatIdentityService(session).delete_identity(user.id, platform)
    response.status_code = _chat_status_code(result.code)
    return result


@internal_router.post("/bind", response_model=ApiResponse[ChatIdentityRead], dependencies=[Depends(require_astrbot_internal)])
async def confirm_binding(payload: InternalChatBindRequest, response: Response, session: AsyncSession = Depends(get_db_session)) -> ApiResponse[ChatIdentityRead]:
    result = await ChatIdentityService(session).confirm_binding(payload.platform, payload.external_id, payload.code)
    response.status_code = _chat_status_code(result.code)
    return result
