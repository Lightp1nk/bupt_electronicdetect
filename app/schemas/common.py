"""Shared result envelope for provider operations."""

from __future__ import annotations

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel


class ErrorCode(str, Enum):
    OK = "OK"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_FAILED = "AUTH_FAILED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    PARSE_ERROR = "PARSE_ERROR"
    NOT_FOUND = "NOT_FOUND"
    BUSINESS_ERROR = "BUSINESS_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CHAT_NOT_BOUND = "CHAT_NOT_BOUND"
    NO_ROOM_CONFIGURED = "NO_ROOM_CONFIGURED"
    NO_DATA = "NO_DATA"


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    code: ErrorCode
    message: str
    data: T | None = None

    @classmethod
    def ok(cls, data: T, message: str = "操作成功") -> "ApiResponse[T]":
        return cls(success=True, code=ErrorCode.OK, message=message, data=data)

    @classmethod
    def error(cls, code: ErrorCode, message: str) -> "ApiResponse[T]":
        return cls(success=False, code=code, message=message)
