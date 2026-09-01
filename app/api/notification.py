from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_current_user
from app.database.database import get_db_session
from app.models.user import User
from app.repositories.notification_binding_repository import NotificationBindingRepository
from app.schemas.common import ApiResponse
from app.schemas.notification import NotificationBindingRead, NotificationBindingUpdate, NotificationPlatform, NotificationProvider
from app.services.app_session_service import utc_now

router=APIRouter(prefix="/api/v1/notification",tags=["notification"])
@router.get("/bindings",response_model=ApiResponse[list[NotificationBindingRead]])
async def bindings(session:AsyncSession=Depends(get_db_session),user:User=Depends(get_current_user)):
    return ApiResponse.ok([NotificationBindingRead.model_validate(x) for x in await NotificationBindingRepository(session).list(user.id)])
@router.put("/bindings",response_model=ApiResponse[NotificationBindingRead])
async def save(payload:NotificationBindingUpdate,session:AsyncSession=Depends(get_db_session),user:User=Depends(get_current_user)):
    value=await NotificationBindingRepository(session).upsert(user.id,payload.provider.value,payload.platform.value,payload.target_id,payload.enabled,utc_now());await session.commit();return ApiResponse.ok(NotificationBindingRead.model_validate(value))
@router.delete("/bindings/{provider}/{platform}",response_model=ApiResponse[None])
async def delete(provider:NotificationProvider,platform:NotificationPlatform,response:Response,session:AsyncSession=Depends(get_db_session),user:User=Depends(get_current_user)):
    await NotificationBindingRepository(session).delete(user.id,provider.value,platform.value);await session.commit();return ApiResponse.ok(None)
