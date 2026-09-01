"""Request and response models for the local, single-user authentication API."""

from enum import Enum

from pydantic import BaseModel, Field, SecretStr


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: SecretStr = Field(min_length=1)


class SessionState(str, Enum):
    AUTHENTICATED = "AUTHENTICATED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    SESSION_EXPIRED = "SESSION_EXPIRED"


class SessionStatus(BaseModel):
    authenticated: bool
    state: SessionState
