"""Outbound notification adapters with no access to electricity or authentication state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from app.models.alert import AlertEvent
from app.models.notification_binding import NotificationBinding
from app.schemas.notification import NotificationStage


@dataclass(frozen=True)
class NotificationSendResult:
    success: bool
    error_message: str | None = None


class NotificationProvider(Protocol):
    async def send(self, binding: NotificationBinding, event: AlertEvent, stage: NotificationStage) -> NotificationSendResult: ...


class AstrBotNotifier:
    """AstrBot adapter boundary.

    AstrBot has no project-verified generic outbound HTTP contract yet.  The
    endpoint/token stay deployment-only configuration; until a documented
    contract is selected this adapter deliberately performs no network I/O.
    """

    def __init__(self, endpoint: str | None = None, token: str | None = None) -> None:
        self._endpoint = endpoint
        self._token = token

    @classmethod
    def from_environment(cls) -> "AstrBotNotifier":
        return cls(os.getenv("ASTRBOT_ENDPOINT"), os.getenv("ASTRBOT_TOKEN"))

    async def send(self, binding: NotificationBinding, event: AlertEvent, stage: NotificationStage) -> NotificationSendResult:
        if not self._endpoint or not self._token:
            return NotificationSendResult(False, "AstrBot notification is not configured")
        return NotificationSendResult(False, "AstrBot outbound API is not configured")


class MockAstrBotNotifier:
    """Deterministic test notifier; production code never selects it implicitly."""

    def __init__(self, result: NotificationSendResult | None = None, exception: Exception | None = None) -> None:
        self.result = result or NotificationSendResult(True)
        self.exception = exception
        self.calls: list[tuple[NotificationBinding, AlertEvent, NotificationStage]] = []

    async def send(self, binding: NotificationBinding, event: AlertEvent, stage: NotificationStage) -> NotificationSendResult:
        self.calls.append((binding, event, stage))
        if self.exception is not None:
            raise self.exception
        return self.result
