"""AstrBot-owned bridge for BUPT electricity notifications.

The FastAPI application only knows a QQ number.  This plugin captures the
platform-native UMO after an explicit private-chat binding and keeps that UMO
inside AstrBot's own plugin data directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

try:
    from .query_client import BUPTElectricityInternalClient, ChatCommandService
except ImportError:  # AstrBot loads plugin main modules directly in some versions.
    from query_client import BUPTElectricityInternalClient, ChatCommandService

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register
from astrbot.api.web import json_response, request
from astrbot.core.star.star_tools import StarTools


PLUGIN_NAME = "buptelec_bridge"
QQ_ID_PATTERN = re.compile(r"^\d{5,20}$")
MAX_MESSAGE_LENGTH = 4_000
APP_ENDPOINT_ENV = "BUPTELEC_APP_ENDPOINT"
BRIDGE_TOKEN_ENV = "BUPTELEC_BRIDGE_TOKEN"
INTERNAL_TOKEN_ENV = "BUPTELEC_INTERNAL_TOKEN"


@register(
    PLUGIN_NAME,
    "Pureastar",
    "Bridge BUPT electricity notifications and private QQ electricity summaries.",
    "0.2.0",
)
class BUPTElectricityBridge(Star):
    """Owns QQ-to-UMO bindings and sends authenticated bridge messages."""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.context = context
        self._lock = asyncio.Lock()
        self._bindings_path = Path(StarTools.get_data_dir(PLUGIN_NAME)) / "qq_umo_bindings.json"
        self._bindings = self._load_bindings()
        self._app_endpoint = os.getenv(APP_ENDPOINT_ENV, "").rstrip("/")
        self._bridge_token = os.getenv(BRIDGE_TOKEN_ENV, "")
        self._internal_client = BUPTElectricityInternalClient(self._app_endpoint, os.getenv(INTERNAL_TOKEN_ENV, ""))
        self._chat_commands = ChatCommandService(self._internal_client)
        context.register_web_api(
            f"/{PLUGIN_NAME}/api/send",
            self.send_from_bridge,
            ["POST"],
            "Send a BUPT electricity notification to a bound QQ private chat.",
        )

    def _load_bindings(self) -> dict[str, str]:
        try:
            raw = json.loads(self._bindings_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            logger.warning("BUPT electricity bridge bindings could not be loaded.")
            return {}

        if not isinstance(raw, dict):
            return {}
        return {
            qq_id: umo
            for qq_id, umo in raw.items()
            if isinstance(qq_id, str)
            and QQ_ID_PATTERN.fullmatch(qq_id)
            and isinstance(umo, str)
            and umo
        }

    def _persist_bindings(self) -> None:
        self._bindings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._bindings_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(self._bindings, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(self._bindings_path)

    async def _is_enabled_notification_target(self, qq_id: str) -> bool | None:
        """Check that the QQ target was saved and enabled before binding it."""
        if not self._app_endpoint or not self._bridge_token:
            return None
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._app_endpoint}/api/v1/notification/bridge/bindings/{qq_id}",
                    headers={"Authorization": f"Bearer {self._bridge_token}"},
                )
            if response.status_code != 200:
                return None
            payload = response.json()
            return bool(isinstance(payload, dict) and isinstance(payload.get("data"), dict) and payload["data"].get("eligible"))
        except (httpx.HTTPError, ValueError):
            logger.warning("BUPT electricity bridge binding validation failed.")
            return None

    @staticmethod
    def _private_qq_id(event: AstrMessageEvent) -> str | None:
        qq_id = str(event.get_sender_id() or "").strip()
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        return qq_id if QQ_ID_PATTERN.fullmatch(qq_id) and "FriendMessage" in umo else None

    @staticmethod
    def _command_argument(event: AstrMessageEvent, command: str) -> str:
        message = str(getattr(event, "message_str", "") or "").strip().lstrip("/")
        if not message.startswith(command):
            return ""
        return message[len(command):].strip().split(maxsplit=1)[0] if message[len(command):].strip() else ""

    @filter.command("绑定")
    async def bind_chat_identity(self, event: AstrMessageEvent):
        """Confirm a short-lived Web-generated QQ identity binding code."""
        code = self._command_argument(event, "绑定")
        yield event.plain_result(await self._chat_commands.bind_reply(self._private_qq_id(event), code))

    @filter.command("电费", alias=["查询电费"])
    async def electricity_summary(self, event: AstrMessageEvent):
        """Return the sender's saved electricity snapshot without upstream refresh."""
        yield event.plain_result(await self._chat_commands.summary_reply(self._private_qq_id(event)))

    @filter.command("电费绑定")
    async def bind_private_chat(self, event: AstrMessageEvent):
        """Bind the sender's QQ number to the current private-chat UMO."""
        qq_id = str(event.get_sender_id() or "").strip()
        umo = str(getattr(event, "unified_msg_origin", "") or "").strip()

        if not QQ_ID_PATTERN.fullmatch(qq_id) or "FriendMessage" not in umo:
            yield event.plain_result("请在与机器人的 QQ 私聊中发送 /电费绑定。")
            return

        enabled = await self._is_enabled_notification_target(qq_id)
        if enabled is None:
            yield event.plain_result("通知绑定校验服务暂不可用，请稍后重试。")
            return
        if not enabled:
            yield event.plain_result("请先在北邮电费查询系统中保存并启用当前 QQ 号，再发送 /电费绑定。")
            return

        async with self._lock:
            self._bindings[qq_id] = umo
            try:
                self._persist_bindings()
            except OSError:
                logger.warning("BUPT electricity bridge binding could not be saved.")
                yield event.plain_result("绑定保存失败，请稍后重试。")
                return

        yield event.plain_result("北邮电费通知已绑定到当前私聊。")

    async def send_from_bridge(self) -> Any:
        """Accept a protected Bridge request from the FastAPI application."""
        payload = await request.json(default=None)
        if not isinstance(payload, dict):
            return json_response({"success": False, "message": "invalid JSON body"}, status_code=400)

        platform = payload.get("platform")
        target_id = str(payload.get("target_id") or "").strip()
        message = payload.get("message")
        if platform != "qq" or not QQ_ID_PATTERN.fullmatch(target_id):
            return json_response({"success": False, "message": "invalid notification target"}, status_code=400)
        if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE_LENGTH:
            return json_response({"success": False, "message": "invalid notification message"}, status_code=400)

        async with self._lock:
            umo = self._bindings.get(target_id)
        if not umo:
            return json_response({"success": False, "message": "QQ target is not bound"}, status_code=404)

        try:
            delivered = await self.context.send_message(umo, MessageChain([Plain(message.strip())]))
        except Exception:
            logger.warning("BUPT electricity bridge delivery failed.")
            return json_response({"success": False, "message": "delivery failed"}, status_code=502)
        if not delivered:
            return json_response({"success": False, "message": "no matching platform"}, status_code=502)
        return json_response({"success": True})
