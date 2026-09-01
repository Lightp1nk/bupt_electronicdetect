"""Normalized electricity reading while retaining every upstream field."""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ElectricityReading(BaseModel):
    area_id: str
    building_id: str
    building_name: str | None = None
    floor_id: str
    floor_name: str | None = None
    room_id: str
    room_name: str | None = None
    source_time: str | None = None
    remaining_money: float | None = None
    remaining_kwh: float | None = None
    remaining_energy_kwh: float | None = None
    total_usage_kwh: float | None = None
    free_remaining_kwh: float | None = None
    price_per_kwh: float | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)


class ElectricityQueryRequest(BaseModel):
    area_id: str = Field(min_length=1)
    building_id: str = Field(min_length=1)
    floor_id: str = Field(min_length=1)
    room_id: str = Field(min_length=1)
    room_name: str | None = None


class ElectricityRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    area_id: str
    building_id: str
    building_name: str | None = None
    floor_id: str
    floor_name: str | None = None
    room_id: str
    room_name: str | None = None
    remaining_money: float | None = None
    remaining_kwh: float | None = None
    remaining_energy_kwh: float | None = None
    free_remaining_kwh: float | None = None
    total_usage_kwh: float | None = None
    price_per_kwh: float | None = None
    source_time: datetime | None = None
    query_time: datetime
    created_at: datetime
    raw_data_json: dict[str, Any]


class ElectricityQuerySaveResult(BaseModel):
    reading: ElectricityReading
    record: ElectricityRecordRead
    saved: bool
    duplicate: bool


class PredictionMaturity(str, Enum):
    INSUFFICIENT = "insufficient"
    PRELIMINARY = "preliminary"
    STABLE = "stable"


class DailyUsageRead(BaseModel):
    date: date
    usage_kwh: float


class ElectricityAnalysisCurrent(BaseModel):
    remaining_money: float | None = None
    remaining_kwh: float | None = None
    remaining_energy_kwh: float | None = None
    total_usage_kwh: float | None = None
    source_time: datetime | None = None


class ElectricityUsageStatistics(BaseModel):
    valid_daily_count: int
    avg_3d_kwh: float | None = None
    avg_7d_kwh: float | None = None


class ElectricityUsagePrediction(BaseModel):
    estimated_remaining_days: float | None = None
    average_daily_usage_kwh: float | None = None
    window_days: int | None = None
    maturity: PredictionMaturity


class ElectricityAnalysis(BaseModel):
    area_id: str
    room_id: str
    current: ElectricityAnalysisCurrent
    statistics: ElectricityUsageStatistics
    prediction: ElectricityUsagePrediction
    daily_usage: list[DailyUsageRead]


class CollectionStatus(str, Enum):
    NEVER_RUN = "never_run"
    SUCCESS = "success"
    NO_ROOM_CONFIGURED = "no_room_configured"
    NOT_AUTHENTICATED = "not_authenticated"
    SESSION_EXPIRED = "session_expired"
    UPSTREAM_NOT_UPDATED = "upstream_not_updated"
    FAILED = "failed"
    ALREADY_RUNNING = "already_running"


class CollectionSettingsUpdate(BaseModel):
    area_id: str = Field(min_length=1)
    building_id: str = Field(min_length=1)
    building_name: str = Field(min_length=1)
    floor_id: str = Field(min_length=1)
    floor_name: str = Field(min_length=1)
    room_id: str = Field(min_length=1)
    room_name: str = Field(min_length=1)


class CollectionStatusRead(BaseModel):
    enabled: bool
    scheduled_time: str
    authenticated: bool
    area_id: str | None = None
    building_id: str | None = None
    building_name: str | None = None
    floor_id: str | None = None
    floor_name: str | None = None
    room_id: str | None = None
    room_name: str | None = None
    status: CollectionStatus
    message: str | None = None
    last_attempt_time: datetime | None = None
    last_success_time: datetime | None = None
    last_source_time: datetime | None = None
