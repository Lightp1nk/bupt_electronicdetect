from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_user
from app.database.database import get_db_session
from app.models.user import User
from app.repositories.notification_binding_repository import NotificationBindingRepository
from app.repositories.notification_delivery_repository import NotificationDeliveryRepository
from app.schemas.common import ApiResponse
from app.schemas.notification import NotificationBindingRead, NotificationBindingUpdate, NotificationDeliveryStatus, NotificationPlatform, NotificationProvider, NotificationStage, NotificationStatusRead
from app.services.app_session_service import utc_now
from app.services.bridge_auth import require_astrbot_bridge

router=APIRouter(prefix="/api/v1/notification",tags=["notification"])
@router.get("/bridge/bindings/{target_id}", response_model=ApiResponse[dict[str, bool]], dependencies=[Depends(require_astrbot_bridge)])
async def bridge_binding_eligibility(target_id: str, session: AsyncSession = Depends(get_db_session)):
    """Expose only whether the Bridge may bind this explicitly enabled QQ target."""
    eligible = target_id.isdigit() and 5 <= len(target_id) <= 20 and await NotificationBindingRepository(session).has_enabled_target(
        NotificationProvider.ASTRBOT.value, NotificationPlatform.QQ.value, target_id,
    )
    return ApiResponse.ok({"eligible": eligible})

@router.get("/bindings",response_model=ApiResponse[list[NotificationBindingRead]])
async def bindings(session:AsyncSession=Depends(get_db_session),user:User=Depends(get_current_user)):
    return ApiResponse.ok([NotificationBindingRead.model_validate(x) for x in await NotificationBindingRepository(session).list(user.id)])
@router.put("/bindings",response_model=ApiResponse[NotificationBindingRead])
async def save(payload:NotificationBindingUpdate,session:AsyncSession=Depends(get_db_session),user:User=Depends(get_current_user)):
    value=await NotificationBindingRepository(session).upsert(user.id,payload.provider.value,payload.platform.value,payload.target_id,payload.enabled,utc_now());await session.commit();return ApiResponse.ok(NotificationBindingRead.model_validate(value))
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
@router.delete("/bindings/{provider}/{platform}",response_model=ApiResponse[None])
async def delete(provider:NotificationProvider,platform:NotificationPlatform,response:Response,session:AsyncSession=Depends(get_db_session),user:User=Depends(get_current_user)):
    await NotificationBindingRepository(session).delete(user.id,provider.value,platform.value);await session.commit();return ApiResponse.ok(None)
