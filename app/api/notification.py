from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_user
from app.database.database import get_db_session
from app.models.user import User
from app.repositories.notification_binding_repository import NotificationBindingRepository
from app.repositories.chat_identity_repository import ChatIdentityRepository
from app.repositories.notification_delivery_repository import NotificationDeliveryRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.notification import NotificationBindingEnabledUpdate, NotificationBindingRead, NotificationDeliveryStatus, NotificationPlatform, NotificationProvider, NotificationStage, NotificationStatusRead
from app.services.app_session_service import utc_now

router=APIRouter(prefix="/api/v1/notification",tags=["notification"])

@router.get("/bindings",response_model=ApiResponse[list[NotificationBindingRead]])
async def bindings(session:AsyncSession=Depends(get_db_session),user:User=Depends(get_current_user)):
    return ApiResponse.ok([NotificationBindingRead.model_validate(x) for x in await NotificationBindingRepository(session).list(user.id)])
@router.put("/bindings/astrbot/qq/enabled",response_model=ApiResponse[NotificationBindingRead])
async def set_astrbot_qq_enabled(payload: NotificationBindingEnabledUpdate, response: Response, session: AsyncSession = Depends(get_db_session), user: User = Depends(get_current_user)):
    """Toggle delivery for the verified QQ identity without accepting a QQ ID."""
    identity = await ChatIdentityRepository(session).get_identity(user.id, NotificationPlatform.QQ.value)
    if identity is None:
        response.status_code = 404
        return ApiResponse.error(ErrorCode.CHAT_NOT_BOUND, "bind QQ in AstrBot before enabling notifications")
    value = await NotificationBindingRepository(session).upsert(
        user.id, NotificationProvider.ASTRBOT.value, NotificationPlatform.QQ.value,
        identity.external_id, payload.enabled, utc_now(),
    )
    await session.commit()
    return ApiResponse.ok(NotificationBindingRead.model_validate(value))
@router.get("/status",response_model=ApiResponse[NotificationStatusRead])
async def status(session:AsyncSession=Depends(get_db_session),user:User=Depends(get_current_user)):
    binding = next((item for item in await NotificationBindingRepository(session).list(user.id) if item.provider == NotificationProvider.ASTRBOT.value and item.platform == NotificationPlatform.QQ.value), None)
    latest = await NotificationDeliveryRepository(session).latest_for_user(user.id)
    return ApiResponse.ok(NotificationStatusRead(
        configured=binding is not None,
        enabled=bool(binding and binding.enabled),
        last_delivery_status=NotificationDeliveryStatus(latest.status) if latest else None,
        last_delivery_stage=NotificationStage(latest.stage) if latest else None,
        last_delivery_time=(latest.sent_at or latest.created_at) if latest else None,
    ))
