from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class NotificationProvider(str, Enum): ASTRBOT = "astrbot"
class NotificationPlatform(str, Enum): QQ = "qq"
class NotificationStage(str, Enum): ACTIVATED = "activated"; ESCALATED = "escalated"; RESOLVED = "resolved"
class NotificationDeliveryStatus(str, Enum): PENDING = "pending"; SUCCESS = "success"; FAILED = "failed"
class NotificationBindingUpdate(BaseModel):
    provider: NotificationProvider
    platform: NotificationPlatform
    target_id: str = Field(pattern=r"^\d{5,20}$")
    enabled: bool
class NotificationBindingRead(NotificationBindingUpdate):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime

class NotificationStatusRead(BaseModel):
    configured: bool
    enabled: bool
    last_delivery_status: NotificationDeliveryStatus | None = None
    last_delivery_stage: NotificationStage | None = None
    last_delivery_time: datetime | None = None
