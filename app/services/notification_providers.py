"""Outbound notification adapters with no access to electricity or authentication state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.models.alert import AlertEvent
from app.models.notification_binding import NotificationBinding
from app.schemas.notification import NotificationStage


@dataclass(frozen=True)
class NotificationSendResult:
    success: bool
    error_message: str | None = None


class NotificationProvider(Protocol):
    async def send(self, binding: NotificationBinding, event: AlertEvent, stage: NotificationStage) -> NotificationSendResult: ...


class AstrBotBridgeNotifier:
    """Send QQ-targeted messages to a trusted internal AstrBot Bridge.

    The Bridge owns QQ-ID-to-UMO resolution and AstrBot's official API token.
    This application only transmits a QQ target and a plain-text alert; it never
    constructs, stores, or observes an AstrBot UMO.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        token: str | None = None,
        *,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/") if endpoint else None
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @classmethod
    def from_environment(cls) -> "AstrBotBridgeNotifier":
        return cls(os.getenv("ASTRBOT_BRIDGE_ENDPOINT"), os.getenv("ASTRBOT_BRIDGE_TOKEN"))

    async def send(self, binding: NotificationBinding, event: AlertEvent, stage: NotificationStage) -> NotificationSendResult:
        if not self._endpoint:
            return NotificationSendResult(False, "AstrBot bridge is not configured")
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        payload = {"platform": binding.platform, "target_id": binding.target_id, "message": self.format_message(event, stage)}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = await client.post(f"{self._endpoint}/api/send", json=payload, headers=headers)
            if 200 <= response.status_code < 300:
                return NotificationSendResult(True)
            return NotificationSendResult(False, "AstrBot bridge returned an error")
        except httpx.TimeoutException:
            return NotificationSendResult(False, "AstrBot bridge timed out")
        except httpx.HTTPError:
            return NotificationSendResult(False, "AstrBot bridge request failed")

    @staticmethod
    def format_message(event: AlertEvent, stage: NotificationStage) -> str:
        level = "严重" if event.level == "critical" else "警告"
        source_time = event.source_time.strftime("%Y-%m-%d %H:%M") if event.source_time else "—"
        return (
            "⚡ 北邮电费提醒\n\n"
            f"宿舍：{event.room_name or event.room_id}\n"
            f"事件：{event.title}\n"
            f"等级：{level}\n"
            f"内容：{event.message}\n"
            f"时间：{source_time}"
        )


class MockAstrBotBridgeNotifier:
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


# Compatibility for existing tests and injection points; both implement the
# same bridge-facing provider contract and neither contacts AstrBot directly.
MockAstrBotNotifier = MockAstrBotBridgeNotifier
