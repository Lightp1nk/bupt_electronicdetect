from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from app.providers.bupt_client import BUPTClient
from app.schemas.common import ErrorCode


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def make_client(handler: Any) -> BUPTClient:
    return BUPTClient(transport=httpx.MockTransport(handler))


def success_response(data: Any) -> httpx.Response:
    return httpx.Response(200, json={"e": 0, "m": "操作成功", "d": {"data": data}})


def test_buildings_parse_internal_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/part")
        assert request.content == b"areaid=2"
        return success_response([{"partmentId": "internal-b", "partmentName": "雁北园B楼"}])

    async def scenario() -> None:
        async with make_client(handler) as client:
            result = await client.get_buildings(area_id="2")
        assert result.success
        assert result.data[0].id == "internal-b"
        assert result.data[0].name == "雁北园B楼"

    run(scenario())


@pytest.mark.parametrize("payload", [
    {"e": 1, "m": "权限不足", "d": {"data": []}},
    {"e": 0, "m": "操作成功"},
    {"e": 0, "m": "操作成功", "d": {}},
])
def test_upstream_business_and_shape_errors(payload: dict[str, Any]) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def scenario() -> None:
        async with make_client(handler) as client:
            result = await client.get_buildings(area_id="1")
        assert not result.success
        assert result.code in {ErrorCode.BUSINESS_ERROR, ErrorCode.PARSE_ERROR}

    run(scenario())


@pytest.mark.parametrize(
    ("price", "surplus", "expected_price", "expected_money", "expected_kwh"),
    [
        ("0.48", "47.14", 0.48, 47.14, pytest.approx(47.14 / 0.48)),
        ("", "", None, None, None),
        ("not-a-number", "invalid", None, None, None),
    ],
)
def test_search_numeric_normalization(
    price: str, surplus: str, expected_price: float | None, expected_money: float | None, expected_kwh: Any
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return success_response({"price": price, "surplus": surplus, "freeEnd": "5204.73", "time": "t", "parName": "B楼", "floorName": "2"})

    async def scenario() -> None:
        async with make_client(handler) as client:
            result = await client.query_electricity(area_id="2", building_id="b", floor_id="f", room_id="r", room_name="203")
        assert result.success
        reading = result.data
        assert reading.price_per_kwh == expected_price
        assert reading.remaining_money == expected_money
        assert reading.remaining_kwh == expected_kwh
        assert reading.total_usage_kwh == 5204.73

    run(scenario())


def test_session_expired_redirect() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/uc/wap/login"})

    async def scenario() -> None:
        async with make_client(handler) as client:
            result = await client.get_buildings(area_id="1")
        assert result.code == ErrorCode.SESSION_EXPIRED

    run(scenario())


def test_timeout_and_invalid_json() -> None:
    async def timeout_handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    async def invalid_json_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})

    async def scenario() -> None:
        async with make_client(timeout_handler) as client:
            timed_out = await client.get_buildings(area_id="1")
        async with make_client(invalid_json_handler) as client:
            invalid_json = await client.get_buildings(area_id="1")
        assert timed_out.code == ErrorCode.TIMEOUT
        assert invalid_json.code == ErrorCode.PARSE_ERROR

    run(scenario())
