"""FastAPI application with user-scoped in-memory BUPT runtime sessions."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.electricity import router as electricity_router
from app.api.notification import router as notification_router
from app.api.errors import ApiError
from app.database.database import SessionLocal, dispose_db, init_db
from app.schemas.common import ApiResponse, ErrorCode
from app.services.auth_session import AuthSessionManager
from app.services.upstream_session_service import UpstreamSessionService
from app.services.app_session_service import AppSessionConfig
from app.services.collection_scheduler import CollectionScheduleConfig, MultiUserCollectionScheduler, start_collection_scheduler
from app.services.collection_service import CollectionService
from app.services.monitoring_service import MonitoringService
from app.services.notification_providers import AstrBotNotifier


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    app.state.app_session_config = AppSessionConfig.from_environment()
    app.state.upstream_session_service = UpstreamSessionService(SessionLocal)
    app.state.auth_session_manager = AuthSessionManager(
        runtime_session_loader=app.state.upstream_session_service.load_business_session,
        runtime_cookie_persister=app.state.upstream_session_service.persist_runtime_cookies,
        runtime_marker=app.state.upstream_session_service.mark_validated,
        runtime_expiry_marker=app.state.upstream_session_service.mark_reauth_required,
    )
    app.state.monitoring_service = MonitoringService(notification_provider=AstrBotNotifier.from_environment())
    schedule_config = CollectionScheduleConfig.from_environment()
    app.state.collection_service = CollectionService(
        SessionLocal, app.state.auth_session_manager, app.state.monitoring_service,
        enabled=schedule_config.enabled, hour=schedule_config.hour, minute=schedule_config.minute,
    )
    app.state.multi_user_collection_scheduler = MultiUserCollectionScheduler(
        SessionLocal, app.state.collection_service, max_concurrency=schedule_config.max_concurrency,
    )
    app.state.collection_scheduler = start_collection_scheduler(app.state.multi_user_collection_scheduler, schedule_config)
    try:
        yield
    finally:
        app.state.collection_scheduler.shutdown(wait=False)
        await app.state.auth_session_manager.close_all()
        await dispose_db()


app = FastAPI(title="BUPT Dormitory Electricity Monitor", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(electricity_router)
app.include_router(notification_router)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    status_code = 401 if exc.code in {ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_EXPIRED, ErrorCode.REAUTH_REQUIRED} else 502
    body = ApiResponse[None].error(exc.code, exc.message).model_dump(mode="json")
    return JSONResponse(status_code=status_code, content=body)
