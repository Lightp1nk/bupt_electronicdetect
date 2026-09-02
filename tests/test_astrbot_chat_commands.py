import asyncio
import json

import httpx

from astrbot_plugins.buptelec_bridge.query_client import BUPTElectricityInternalClient, ChatCommandService


def test_astrbot_chat_commands_use_mock_http_and_format_private_summary() -> None:
    async def scenario() -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if request.url.path.endswith("/bind"):
                return httpx.Response(200, json={"success": True, "code": "OK", "message": "bound", "data": {"platform": "qq", "external_id": "123456"}})
            return httpx.Response(200, json={"success": True, "code": "OK", "message": "ok", "data": {"room_name": "沙河 · A楼 · 419", "balance": 47.14, "remaining_kwh": 12.5, "total_usage_kwh": 5204.73, "source_time": "2026-09-02T04:00:00", "estimated_remaining_days": 12.5, "maturity": "stable"}})

        client = BUPTElectricityInternalClient("http://internal.test", "token", transport=httpx.MockTransport(handler))
        commands = ChatCommandService(client)
        assert "绑定成功" in await commands.bind_reply("123456", "ABCDE-FGHIJ")
        reply = await commands.summary_reply("123456")
        assert "⚡ 北邮电费查询" in reply and "¥47.14" in reply and "12.5 天" in reply
        assert all(request.headers["Authorization"] == "Bearer token" for request in seen)
        assert json.loads(seen[-1].content) == {"platform": "qq", "external_id": "123456"}
        assert await commands.summary_reply(None) == "请私聊机器人查询电费。"

    asyncio.run(scenario())


def test_astrbot_chat_command_error_paths_do_not_leak_internal_details() -> None:
    async def scenario() -> None:
        def not_bound(_: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"success": False, "code": "CHAT_NOT_BOUND", "message": "ignored"})

        commands = ChatCommandService(BUPTElectricityInternalClient("http://internal.test", "token", transport=httpx.MockTransport(not_bound)))
        assert "生成绑定码" in await commands.summary_reply("123456")

        def failure(_: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out")

        timed_out = ChatCommandService(BUPTElectricityInternalClient("http://internal.test", "token", transport=httpx.MockTransport(failure)))
        assert "超时" in await timed_out.summary_reply("123456")
        assert "私聊" in await commands.bind_reply(None, "ABCDE-FGHIJ")

    asyncio.run(scenario())
