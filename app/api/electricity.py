"""One minimal protected business route used to verify session reuse."""

from fastapi import APIRouter, Depends, Response

from app.api.auth import _status_code
from app.api.dependencies import get_authenticated_bupt_client
from app.providers.bupt_client import BUPTClient
from app.schemas.common import ApiResponse
from app.schemas.dormitory import Building


router = APIRouter(prefix="/api/v1/electricity", tags=["electricity"])


@router.get("/buildings", response_model=ApiResponse[list[Building]])
async def buildings(
    area_id: str,
    response: Response,
    client: BUPTClient = Depends(get_authenticated_bupt_client),
) -> ApiResponse[list[Building]]:
    result = await client.get_buildings(area_id=area_id)
    response.status_code = _status_code(result.code)
    return result
