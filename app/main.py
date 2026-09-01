"""FastAPI application with an in-memory, single-user BUPT session."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.electricity import router as electricity_router
from app.api.errors import ApiError
from app.database.database import SessionLocal, dispose_db, init_db
from app.schemas.common import ApiResponse, ErrorCode
from app.services.auth_session import AuthSessionManager
from app.services.collection_scheduler import CollectionScheduleConfig, start_collection_scheduler
from app.services.collection_service import CollectionService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    app.state.auth_session_manager = AuthSessionManager()
    schedule_config = CollectionScheduleConfig.from_environment()
    app.state.collection_service = CollectionService(
        SessionLocal, app.state.auth_session_manager,
        enabled=schedule_config.enabled, hour=schedule_config.hour, minute=schedule_config.minute,
    )
    app.state.collection_scheduler = start_collection_scheduler(app.state.collection_service, schedule_config)
    try:
        yield
    finally:
        app.state.collection_scheduler.shutdown(wait=False)
        await app.state.auth_session_manager.logout()
        await dispose_db()


app = FastAPI(title="BUPT Dormitory Electricity Monitor", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(electricity_router)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    status_code = 401 if exc.code in {ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_EXPIRED} else 502
    body = ApiResponse[None].error(exc.code, exc.message).model_dump(mode="json")
    return JSONResponse(status_code=status_code, content=body)
