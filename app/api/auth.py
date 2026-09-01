"""Local API routes that control the sole in-memory BUPT session."""

from fastapi import APIRouter, Request, Response

from app.schemas.auth import LoginRequest, SessionStatus
from app.schemas.common import ApiResponse, ErrorCode


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[SessionStatus])
async def login(payload: LoginRequest, request: Request, response: Response) -> ApiResponse[SessionStatus]:
    result = await request.app.state.auth_session_manager.login(payload.username, payload.password.get_secret_value())
    response.status_code = _status_code(result.code)
    return result


@router.get("/status", response_model=ApiResponse[SessionStatus])
async def status(request: Request, response: Response) -> ApiResponse[SessionStatus]:
    result = await request.app.state.auth_session_manager.status()
    response.status_code = _status_code(result.code)
    return result


@router.post("/logout", response_model=ApiResponse[SessionStatus])
async def logout(request: Request) -> ApiResponse[SessionStatus]:
    return await request.app.state.auth_session_manager.logout()


def _status_code(code: ErrorCode) -> int:
    if code == ErrorCode.OK:
        return 200
    if code in {ErrorCode.AUTH_FAILED, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_EXPIRED}:
        return 401
    if code == ErrorCode.INVALID_ARGUMENT:
        return 400
    if code in {ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT, ErrorCode.UPSTREAM_ERROR}:
        return 502
    return 500
