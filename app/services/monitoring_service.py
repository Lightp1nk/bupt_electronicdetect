"""Shared query → snapshot save → alert evaluation orchestration."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.providers.bupt_client import BUPTClient
from app.schemas.common import ApiResponse
from app.schemas.electricity import ElectricityQuerySaveResult
from app.services.alert_service import AlertService
from app.services.electricity_service import ElectricityService

class MonitoringService:
    def __init__(self, _legacy_lock: object | None = None) -> None:
        """Keep an ignored compatibility parameter while removing global serialization."""

    async def query_save_and_evaluate(self, user_id: int, session: AsyncSession, client: BUPTClient, **room: str) -> ApiResponse[ElectricityQuerySaveResult]:
        # RuntimeSessionManager serializes a single user's upstream Client lease.
        # No global lock belongs here: distinct users may query concurrently.
        result = await ElectricityService(session).query_and_save(client, **room)
        if result.success and result.data is not None:
            await AlertService(session).evaluate(user_id, result.data.reading)
        return result
