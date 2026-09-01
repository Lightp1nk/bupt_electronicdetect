"""Shared query → snapshot save → alert evaluation orchestration for one process."""
from __future__ import annotations
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.providers.bupt_client import BUPTClient
from app.schemas.common import ApiResponse
from app.schemas.electricity import ElectricityQuerySaveResult
from app.services.alert_service import AlertService
from app.services.electricity_service import ElectricityService

class MonitoringService:
    def __init__(self, lock: asyncio.Lock) -> None: self._lock = lock
    async def query_save_and_evaluate(self, session: AsyncSession, client: BUPTClient, **room: str) -> ApiResponse[ElectricityQuerySaveResult]:
        async with self._lock:
            result = await ElectricityService(session).query_and_save(client, **room)
            if result.success and result.data is not None: await AlertService(session).evaluate(result.data.reading)
            return result
