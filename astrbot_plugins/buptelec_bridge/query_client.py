"""HTTP client and formatting used by the AstrBot chat commands.

This module deliberately depends on httpx only, so it can be tested without
the AstrBot runtime or a live QQ connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


@dataclass(frozen=True)
class InternalResult:
    success: bool
    code: str
    message: str
    data: dict[str, Any] | None = None


class BUPTElectricityInternalClient:
    def __init__(self, endpoint: str | None, token: str | None, *, timeout_seconds: float = 5.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._endpoint = endpoint.rstrip("/") if endpoint else None
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def bind(self, qq_id: str, code: str) -> InternalResult:
        return await self._post("/api/internal/chat/bind", {"platform": "qq", "external_id": qq_id, "code": code})

    async def electricity_summary(self, qq_id: str) -> InternalResult:
        return await self._post("/api/internal/chat/electricity/summary", {"platform": "qq", "external_id": qq_id})

    async def _post(self, path: str, payload: dict[str, str]) -> InternalResult:
        if not self._endpoint or not self._token:
            return InternalResult(False, "SERVICE_UNAVAILABLE", "internal API is not configured")
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds, transport=self._transport) as client:
                response = await client.post(f"{self._endpoint}{path}", json=payload, headers={"Authorization": f"Bearer {self._token}"})
            body = response.json()
            if not isinstance(body, dict):
                return InternalResult(False, "SERVICE_ERROR", "invalid internal API response")
            data = body.get("data") if isinstance(body.get("data"), dict) else None
            return InternalResult(bool(body.get("success")), str(body.get("code") or "SERVICE_ERROR"), str(body.get("message") or ""), data)
        except httpx.TimeoutException:
            return InternalResult(False, "TIMEOUT", "internal API timed out")
        except (httpx.HTTPError, ValueError):
            return InternalResult(False, "SERVICE_ERROR", "internal API request failed")


def format_electricity_summary(summary: dict[str, Any]) -> str:
    def amount(value: Any, suffix: str) -> str:
        return f"{float(value):.2f} {suffix}" if value is not None else "暂无数据"

    source_time = summary.get("source_time")
    if isinstance(source_time, str):
        source_text = source_time.replace("T", " ")[:16]
    elif isinstance(source_time, datetime):
        source_text = source_time.strftime("%Y-%m-%d %H:%M")
    else:
        source_text = "暂无数据"
    remaining_days = summary.get("estimated_remaining_days")
    remaining_text = f"{float(remaining_days):.1f} 天" if remaining_days is not None else "数据不足，暂无法预测"
    return (
        "⚡ 北邮电费查询\n\n"
        f"宿舍：{summary.get('room_name') or '已配置宿舍'}\n\n"
        f"当前余额：{('¥' + format(float(summary['balance']), '.2f')) if summary.get('balance') is not None else '暂无数据'}\n\n"
        f"剩余电量：{amount(summary.get('remaining_kwh'), 'kWh')}\n\n"
        f"累计用电：{amount(summary.get('total_usage_kwh'), 'kWh')}\n\n"
        f"预计剩余：{remaining_text}\n\n"
        f"数据时间：{source_text}"
    )


def query_error_message(code: str) -> str:
    messages = {
        "CHAT_NOT_BOUND": "请先在网页中生成绑定码，并在私聊发送 /绑定 绑定码。",
        "NO_ROOM_CONFIGURED": "请先在网页设置监测宿舍。",
        "NO_DATA": "暂无电费数据，请等待首次采集。",
        "TIMEOUT": "查询服务响应超时，请稍后重试。",
    }
    return messages.get(code, "查询服务暂不可用，请稍后重试。")


class ChatCommandService:
    """AstrBot command decisions, kept SDK-free for deterministic testing."""

    def __init__(self, client: BUPTElectricityInternalClient) -> None:
        self._client = client

    async def bind_reply(self, qq_id: str | None, code: str) -> str:
        if qq_id is None:
            return "请在与机器人的 QQ 私聊中发送 /绑定 绑定码。"
        if not code:
            return "请先在网页生成绑定码，再发送 /绑定 绑定码。"
        result = await self._client.bind(qq_id, code)
        if result.success:
            return "QQ 绑定成功，AstrBot 通知已自动启用。现在可以发送 /电费 查询已采集的数据。"
        if result.code == "AUTH_FAILED":
            return "绑定码无效或已过期，请回网页重新生成。"
        if result.code == "BUSINESS_ERROR":
            return "该 QQ 已绑定其他账号，请先在网页解绑后重试。"
        return "绑定服务暂不可用，请稍后重试。"

    async def summary_reply(self, qq_id: str | None) -> str:
        if qq_id is None:
            return "请私聊机器人查询电费。"
        result = await self._client.electricity_summary(qq_id)
        if result.success and result.data is not None:
            return format_electricity_summary(result.data)
        return query_error_message(result.code)
