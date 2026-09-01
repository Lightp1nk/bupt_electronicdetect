import asyncio
from datetime import datetime

import httpx

from app.models.alert import AlertEvent
from app.models.notification_binding import NotificationBinding
from app.schemas.notification import NotificationStage
from app.services.notification_providers import AstrBotBridgeNotifier


def binding(target_id: str = "123456789") -> NotificationBinding:
    return NotificationBinding(
        id=1, user_id=1, provider="astrbot", platform="qq", target_id=target_id,
        enabled=True, created_at=datetime(2026, 9, 1), updated_at=datetime(2026, 9, 1),
    )


def event() -> AlertEvent:
    now = datetime(2026, 9, 1, 4, 0)
    return AlertEvent(
        id=7, user_id=1, area_id="2", room_id="419", building_name="雁北园A楼", floor_name="4层", room_name="A楼419",
        alert_type="low_balance", level="critical", status="active", title="余额不足", message="余额不足：当前 4.00 元，阈值 5.00 元",
        trigger_value=4.0, threshold_value=5.0, source_time=now, first_triggered_at=now, last_seen_at=now,
        resolved_at=None, created_at=now, updated_at=now,
    )


def test_bridge_posts_only_qq_target_and_stable_message() -> None:
    async def scenario() -> None:
        received: dict[str, object] = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            received["url"] = str(request.url)
            received["authorization"] = request.headers.get("Authorization")
            received["body"] = __import__("json").loads(request.content)
            return httpx.Response(204, request=request)

        notifier = AstrBotBridgeNotifier("http://bridge.test", "bridge-secret", transport=httpx.MockTransport(handler))
        result = await notifier.send(binding(), event(), NotificationStage.ACTIVATED)
        assert result.success
        assert received["url"] == "http://bridge.test/api/send"
        assert received["authorization"] == "Bearer bridge-secret"
        assert received["body"] == {
            "platform": "qq", "target_id": "123456789",
            "message": "⚡ 北邮电费提醒\n\n宿舍：A楼419\n事件：余额不足\n等级：严重\n内容：余额不足：当前 4.00 元，阈值 5.00 元\n时间：2026-09-01 04:00",
        }

    asyncio.run(scenario())


def test_bridge_failure_timeout_and_missing_configuration_never_raise() -> None:
    async def scenario() -> None:
        async def error_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, request=request)

        async def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timeout", request=request)

        failed = await AstrBotBridgeNotifier("http://bridge.test", transport=httpx.MockTransport(error_handler)).send(binding(), event(), NotificationStage.ACTIVATED)
        timed_out = await AstrBotBridgeNotifier("http://bridge.test", transport=httpx.MockTransport(timeout_handler)).send(binding(), event(), NotificationStage.ACTIVATED)
        unavailable = await AstrBotBridgeNotifier().send(binding(), event(), NotificationStage.ACTIVATED)
        assert not failed.success and failed.error_message == "AstrBot bridge returned an error"
        assert not timed_out.success and timed_out.error_message == "AstrBot bridge timed out"
        assert not unavailable.success and unavailable.error_message == "AstrBot bridge is not configured"

    asyncio.run(scenario())
