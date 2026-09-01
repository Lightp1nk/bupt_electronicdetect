"""Request and response models for the local, single-user authentication API."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)


class SessionState(str, Enum):
    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    SESSION_EXPIRED = "SESSION_EXPIRED"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bupt_username: str
    display_name: str | None


class SessionStatus(BaseModel):
    authenticated: bool
    state: SessionState
    user: UserRead | None = None
