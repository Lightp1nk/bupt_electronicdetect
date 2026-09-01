"""Derive daily electricity usage and a simple availability prediction from snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.electricity import ElectricityRecord
from app.repositories.electricity_repository import ElectricityRepository
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.electricity import (
    DailyUsageRead,
    ElectricityAnalysis,
    ElectricityAnalysisCurrent,
    ElectricityUsagePrediction,
    ElectricityUsageStatistics,
    PredictionMaturity,
)


@dataclass(frozen=True)
class UsageSnapshot:
    """The only fields needed by the pure daily-usage calculation."""

    source_time: datetime | None
    total_usage_kwh: float | None
    sequence: int = 0


@dataclass(frozen=True)
class UsageCalculation:
    daily_usage: tuple[DailyUsageRead, ...]
    avg_3d_kwh: float | None
    avg_7d_kwh: float | None
    maturity: PredictionMaturity

    @property
    def valid_daily_count(self) -> int:
        return len(self.daily_usage)

    @property
    def selected_average(self) -> tuple[float | None, int | None]:
        if self.maturity == PredictionMaturity.STABLE:
            return self.avg_7d_kwh, 7
        if self.maturity == PredictionMaturity.PRELIMINARY:
            return self.avg_3d_kwh, 3
        return None, None


class StatisticsService:
    """Read existing snapshots and calculate statistics without persisting derived data."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = ElectricityRepository(session)

    async def get_analysis(self, *, area_id: str, room_id: str) -> ApiResponse[ElectricityAnalysis]:
        if not area_id or not room_id:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, "area_id and room_id are required")
        try:
            records = await self._repository.get_history(area_id, room_id)
            current = await self._repository.get_latest(area_id, room_id)
        except SQLAlchemyError:
            return ApiResponse.error(ErrorCode.DATABASE_ERROR, "analysis history could not be read")
        if current is None:
            return ApiResponse.error(ErrorCode.NOT_FOUND, "no saved electricity history for this room")

        calculation = self.calculate(UsageSnapshot(record.source_time, record.total_usage_kwh, record.id) for record in records)
        average, window_days = calculation.selected_average
        remaining_days = None
        if current.remaining_kwh is not None and average is not None and average > 0:
            remaining_days = round(current.remaining_kwh / average, 2)

        return ApiResponse.ok(ElectricityAnalysis(
            area_id=area_id,
            room_id=room_id,
            current=ElectricityAnalysisCurrent(
                remaining_money=current.remaining_money,
                remaining_kwh=current.remaining_kwh,
                remaining_energy_kwh=current.remaining_energy_kwh,
                total_usage_kwh=current.total_usage_kwh,
                source_time=current.source_time,
            ),
            statistics=ElectricityUsageStatistics(
                valid_daily_count=calculation.valid_daily_count,
                avg_3d_kwh=calculation.avg_3d_kwh,
                avg_7d_kwh=calculation.avg_7d_kwh,
            ),
            prediction=ElectricityUsagePrediction(
                estimated_remaining_days=remaining_days,
                average_daily_usage_kwh=average,
                window_days=window_days,
                maturity=calculation.maturity,
            ),
            daily_usage=list(calculation.daily_usage),
        ))

    @staticmethod
    def calculate(snapshots: Iterable[UsageSnapshot]) -> UsageCalculation:
        """Use each source date's latest valid total, then only adjacent calendar dates."""
        latest_by_date: dict[date, UsageSnapshot] = {}
        for snapshot in snapshots:
            if snapshot.source_time is None or snapshot.total_usage_kwh is None:
                continue
            source_date = snapshot.source_time.date()
            previous = latest_by_date.get(source_date)
            if previous is None or (snapshot.source_time, snapshot.sequence) > (previous.source_time, previous.sequence):
                latest_by_date[source_date] = snapshot

        ordered = sorted(latest_by_date.items())
        daily: list[DailyUsageRead] = []
        for (previous_date, previous), (current_date, current) in zip(ordered, ordered[1:]):
            if (current_date - previous_date).days != 1:
                continue
            usage = current.total_usage_kwh - previous.total_usage_kwh
            if usage < 0:
                continue
            daily.append(DailyUsageRead(date=current_date, usage_kwh=usage))

        count = len(daily)
        avg_3d = round(sum(item.usage_kwh for item in daily[-3:]) / 3, 2) if count >= 3 else None
        avg_7d = round(sum(item.usage_kwh for item in daily[-7:]) / 7, 2) if count >= 7 else None
        maturity = PredictionMaturity.STABLE if count >= 7 else PredictionMaturity.PRELIMINARY if count >= 3 else PredictionMaturity.INSUFFICIENT
        return UsageCalculation(tuple(daily), avg_3d, avg_7d, maturity)
