"""Public and internal schemas for verified QQ chat identities."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ChatPlatform(str, Enum):
    QQ = "qq"


class ChatIdentityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: ChatPlatform
    external_id: str
    verified_at: datetime


class ChatBindingCodeRead(BaseModel):
    code: str
    expires_at: datetime


class InternalChatBindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: ChatPlatform
    external_id: str = Field(pattern=r"^\d{5,20}$")
    code: str = Field(min_length=8, max_length=24, pattern=r"^[A-Za-z0-9-]+$")


class InternalChatSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: ChatPlatform
    external_id: str = Field(pattern=r"^\d{5,20}$")


class ChatElectricitySummaryRead(BaseModel):
    room_name: str
    balance: float | None = None
    remaining_kwh: float | None = None
    total_usage_kwh: float | None = None
    source_time: datetime | None = None
    estimated_remaining_days: float | None = None
    maturity: str
