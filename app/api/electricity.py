"""One minimal protected business route used to verify session reuse."""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _status_code
from app.api.dependencies import get_authenticated_bupt_client
from app.database.database import get_db_session
from app.providers.bupt_client import BUPTClient
from app.schemas.common import ApiResponse
from app.schemas.dormitory import Building, Floor, Room
from app.schemas.electricity import CollectionSettingsUpdate, CollectionStatusRead, ElectricityAnalysis, ElectricityQueryRequest, ElectricityQuerySaveResult, ElectricityRecordRead
from app.services.electricity_service import ElectricityService
from app.services.statistics_service import StatisticsService
from app.services.collection_service import CollectionService


router = APIRouter(prefix="/api/v1/electricity", tags=["electricity"])


def _collection_service(request: Request) -> CollectionService:
    return request.app.state.collection_service


@router.get("/buildings", response_model=ApiResponse[list[Building]])
async def buildings(
    area_id: str,
    response: Response,
    client: BUPTClient = Depends(get_authenticated_bupt_client),
) -> ApiResponse[list[Building]]:
    result = await client.get_buildings(area_id=area_id)
    response.status_code = _status_code(result.code)
    return result


@router.get("/floors", response_model=ApiResponse[list[Floor]])
async def floors(
    area_id: str,
    building_id: str,
    response: Response,
    client: BUPTClient = Depends(get_authenticated_bupt_client),
) -> ApiResponse[list[Floor]]:
    result = await client.get_floors(area_id=area_id, building_id=building_id)
    response.status_code = _status_code(result.code)
    return result


@router.get("/rooms", response_model=ApiResponse[list[Room]])
async def rooms(
    area_id: str,
    building_id: str,
    floor_id: str,
    response: Response,
    client: BUPTClient = Depends(get_authenticated_bupt_client),
) -> ApiResponse[list[Room]]:
    result = await client.get_rooms(area_id=area_id, building_id=building_id, floor_id=floor_id)
    response.status_code = _status_code(result.code)
    return result


@router.post("/query", response_model=ApiResponse[ElectricityQuerySaveResult])
async def query(
    payload: ElectricityQueryRequest,
    response: Response,
    client: BUPTClient = Depends(get_authenticated_bupt_client),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ElectricityQuerySaveResult]:
    result = await ElectricityService(session).query_and_save(
        client,
        area_id=payload.area_id,
        building_id=payload.building_id,
        floor_id=payload.floor_id,
        room_id=payload.room_id,
        room_name=payload.room_name,
    )
    response.status_code = _status_code(result.code)
    return result


@router.get("/history/{room_id}", response_model=ApiResponse[list[ElectricityRecordRead]])
async def history(
    room_id: str,
    area_id: str,
    response: Response,
    days: int | None = Query(default=None, ge=1),
    limit: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[list[ElectricityRecordRead]]:
    result = await ElectricityService(session).get_history(area_id=area_id, room_id=room_id, days=days, limit=limit)
    response.status_code = _status_code(result.code)
    return result


@router.get("/latest/{room_id}", response_model=ApiResponse[ElectricityRecordRead])
async def latest(
    room_id: str,
    area_id: str,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ElectricityRecordRead]:
    result = await ElectricityService(session).get_latest(area_id=area_id, room_id=room_id)
    response.status_code = _status_code(result.code)
    return result


@router.get("/analysis/{room_id}", response_model=ApiResponse[ElectricityAnalysis])
async def analysis(
    room_id: str,
    area_id: str,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ElectricityAnalysis]:
    result = await StatisticsService(session).get_analysis(area_id=area_id, room_id=room_id)
    response.status_code = _status_code(result.code)
    return result


@router.get("/collection/settings", response_model=ApiResponse[CollectionStatusRead])
async def collection_settings(request: Request, response: Response) -> ApiResponse[CollectionStatusRead]:
    result = await _collection_service(request).get_status()
    response.status_code = _status_code(result.code)
    return result


@router.put("/collection/settings", response_model=ApiResponse[CollectionStatusRead])
async def save_collection_settings(
    payload: CollectionSettingsUpdate, request: Request, response: Response,
) -> ApiResponse[CollectionStatusRead]:
    result = await _collection_service(request).save_settings(payload)
    response.status_code = _status_code(result.code)
    return result


@router.delete("/collection/settings", response_model=ApiResponse[CollectionStatusRead])
async def clear_collection_settings(request: Request, response: Response) -> ApiResponse[CollectionStatusRead]:
    result = await _collection_service(request).clear_settings()
    response.status_code = _status_code(result.code)
    return result


@router.get("/collection/status", response_model=ApiResponse[CollectionStatusRead])
async def collection_status(request: Request, response: Response) -> ApiResponse[CollectionStatusRead]:
    result = await _collection_service(request).get_status()
    response.status_code = _status_code(result.code)
    return result


@router.post("/collection/run", response_model=ApiResponse[CollectionStatusRead])
async def run_collection(request: Request, response: Response) -> ApiResponse[CollectionStatusRead]:
    result = await _collection_service(request).run_once()
    response.status_code = _status_code(result.code)
    return result
