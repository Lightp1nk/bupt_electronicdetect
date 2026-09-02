from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict

class NotificationProvider(str, Enum): ASTRBOT = "astrbot"
class NotificationPlatform(str, Enum): QQ = "qq"
class NotificationStage(str, Enum): ACTIVATED = "activated"; ESCALATED = "escalated"; RESOLVED = "resolved"
class NotificationDeliveryStatus(str, Enum): PENDING = "pending"; SUCCESS = "success"; FAILED = "failed"
class NotificationBindingRead(BaseModel):
    """Read-only notification route established by QQ chat verification."""

    model_config = ConfigDict(from_attributes=True)

    provider: NotificationProvider
    platform: NotificationPlatform
    target_id: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class NotificationBindingEnabledUpdate(BaseModel):
    """The QQ target is established by verified chat binding, never typed here."""

    enabled: bool

class NotificationStatusRead(BaseModel):
    configured: bool
    enabled: bool
    last_delivery_status: NotificationDeliveryStatus | None = None
    last_delivery_stage: NotificationStage | None = None
    last_delivery_time: datetime | None = None
