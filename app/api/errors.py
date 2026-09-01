"""Uniform API errors for dependencies and application routes."""

from dataclasses import dataclass

from app.schemas.common import ErrorCode


@dataclass
class ApiError(Exception):
    code: ErrorCode
    message: str
