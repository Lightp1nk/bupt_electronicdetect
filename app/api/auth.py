"""Local API routes that control the sole in-memory BUPT session."""

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request, Response

from app.database.database import get_db_session
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import LoginRequest, SessionState, SessionStatus, UserRead
from app.schemas.common import ApiResponse, ErrorCode
from app.services.app_session_service import SESSION_COOKIE_NAME, generate_token, hash_token, utc_now


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[SessionStatus])
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SessionStatus]:
    manager = request.app.state.auth_session_manager
    bootstrap = await manager.bootstrap_login(payload.username, payload.password.get_secret_value())
    if not bootstrap.success or bootstrap.data is None:
        response.status_code = _status_code(bootstrap.code)
        return ApiResponse.error(bootstrap.code, bootstrap.message)

    config = request.app.state.app_session_config
    raw_token = generate_token()
    now = utc_now()
    expires_at = now + config.ttl
    repository = AuthRepository(session)
    try:
        user = await repository.get_or_create_authenticated_user(bootstrap.data.username, now)
        await repository.create_app_session(
            user_id=user.id, token_hash=hash_token(raw_token), now=now, expires_at=expires_at,
        )
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        response.status_code = 500
        return ApiResponse.error(ErrorCode.DATABASE_ERROR, "application session could not be created")

    activated = await manager.activate_runtime(bootstrap.data.session)
    if not activated.success:
        try:
            await repository.revoke_by_token_hash(hash_token(raw_token), now=utc_now())
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
        response.status_code = 500
        return ApiResponse.error(activated.code, activated.message)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=int(config.ttl.total_seconds()),
        path="/",
        secure=config.secure_cookie,
        httponly=True,
        samesite="lax",
    )
    return ApiResponse.ok(_authenticated_status(user), "Authentication successful")


@router.get("/status", response_model=ApiResponse[SessionStatus])
async def status(
    request: Request, response: Response, session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SessionStatus]:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        return ApiResponse.ok(_unauthenticated_status())
    config = request.app.state.app_session_config
    try:
        user = await AuthRepository(session).get_active_user_by_token_hash(
            hash_token(raw_token), now=utc_now(), last_seen_interval=config.last_seen_interval,
        )
        if user is None:
            return ApiResponse.ok(_unauthenticated_status())
        await session.commit()
        return ApiResponse.ok(_authenticated_status(user))
    except SQLAlchemyError:
        await session.rollback()
        response.status_code = 500
        return ApiResponse.error(ErrorCode.DATABASE_ERROR, "application session status could not be read")


@router.post("/logout", response_model=ApiResponse[SessionStatus])
async def logout(
    request: Request, response: Response, session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[SessionStatus]:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token:
        try:
            await AuthRepository(session).revoke_by_token_hash(hash_token(raw_token), now=utc_now())
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            response.status_code = 500
            return ApiResponse.error(ErrorCode.DATABASE_ERROR, "application session could not be revoked")
    config = request.app.state.app_session_config
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=config.secure_cookie,
        httponly=True,
        samesite="lax",
    )
    return ApiResponse.ok(_unauthenticated_status(), "Logged out")


def _authenticated_status(user: object) -> SessionStatus:
    return SessionStatus(authenticated=True, state=SessionState.AUTHENTICATED, user=UserRead.model_validate(user))


def _unauthenticated_status() -> SessionStatus:
    return SessionStatus(authenticated=False, state=SessionState.UNAUTHENTICATED)


def _status_code(code: ErrorCode) -> int:
    if code == ErrorCode.OK:
        return 200
    if code in {ErrorCode.AUTH_FAILED, ErrorCode.AUTH_REQUIRED, ErrorCode.SESSION_EXPIRED}:
        return 401
    if code == ErrorCode.INVALID_ARGUMENT:
        return 400
    if code == ErrorCode.NOT_FOUND:
        return 404
    if code in {ErrorCode.NETWORK_ERROR, ErrorCode.TIMEOUT, ErrorCode.UPSTREAM_ERROR}:
        return 502
    return 500
