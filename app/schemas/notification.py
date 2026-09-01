from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class NotificationProvider(str, Enum): ASTRBOT = "astrbot"
class NotificationPlatform(str, Enum): QQ = "qq"
class NotificationBindingUpdate(BaseModel):
    provider: NotificationProvider
    platform: NotificationPlatform
    target_id: str = Field(pattern=r"^\d{5,20}$")
    enabled: bool
class NotificationBindingRead(NotificationBindingUpdate):
    model_config = ConfigDict(from_attributes=True)
    created_at: datetime
    updated_at: datetime
