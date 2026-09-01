"""Authenticated, single-session client for the BUPT dormitory electricity APIs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.providers.bupt_auth import AuthErrorKind, AuthFailure, BUPTAuthClient
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.dormitory import Building, Floor, Room
from app.schemas.electricity import ElectricityReading


BASE_URL = "https://app.bupt.edu.cn"
BUSINESS_PREFIX = "/buptdf/wap/default"


class BUPTClient(BUPTAuthClient):
    """BUPT CAS authentication and electricity data access with one cookie jar."""

    async def get_buildings(self, *, area_id: str) -> ApiResponse[list[Building]]:
        invalid = _require_ids(area_id=area_id)
        if invalid:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, invalid)
        result = await self._post_business_api("part", {"areaid": area_id})
        if not result.success:
            return _pass_error(result)
        rows = _as_list(result.data)
        if rows is None:
            return ApiResponse.error(ErrorCode.PARSE_ERROR, "/part response data is not a list")
        try:
            return ApiResponse.ok([
                Building(id=_required_string(row, "partmentId"), name=_required_string(row, "partmentName"), area_id=area_id)
                for row in rows
            ])
        except ValueError as exc:
            return ApiResponse.error(ErrorCode.PARSE_ERROR, str(exc))

    async def check_auth_result(self) -> ApiResponse[bool]:
        """Validate the app session through the confirmed, lightweight ``/part`` call."""
        result = await self._post_business_api("part", {"areaid": "1"})
        if result.success:
            return ApiResponse.ok(True, "session is active")
        return ApiResponse.error(result.code, result.message)

    async def check_authenticated(self) -> bool:
        """Boolean compatibility method used by the established authentication flow."""
        return (await self.check_auth_result()).success

    async def get_floors(self, *, area_id: str, building_id: str) -> ApiResponse[list[Floor]]:
        invalid = _require_ids(area_id=area_id, building_id=building_id)
        if invalid:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, invalid)
        result = await self._post_business_api("floor", {"areaid": area_id, "partmentId": building_id})
        if not result.success:
            return _pass_error(result)
        rows = _as_list(result.data)
        if rows is None:
            return ApiResponse.error(ErrorCode.PARSE_ERROR, "/floor response data is not a list")
        try:
            return ApiResponse.ok([
                Floor(id=_required_string(row, "floorId"), name=_required_string(row, "floorName"), building_id=building_id, area_id=area_id)
                for row in rows
            ])
        except ValueError as exc:
            return ApiResponse.error(ErrorCode.PARSE_ERROR, str(exc))

    async def get_rooms(self, *, area_id: str, building_id: str, floor_id: str) -> ApiResponse[list[Room]]:
        invalid = _require_ids(area_id=area_id, building_id=building_id, floor_id=floor_id)
        if invalid:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, invalid)
        result = await self._post_business_api(
            "drom", {"areaid": area_id, "partmentId": building_id, "floorId": floor_id}
        )
        if not result.success:
            return _pass_error(result)
        rows = _as_list(result.data)
        if rows is None:
            return ApiResponse.error(ErrorCode.PARSE_ERROR, "/drom response data is not a list")
        try:
            return ApiResponse.ok([
                Room(
                    id=_required_string(row, "dromNum"),
                    name=_required_string(row, "dromName"),
                    floor_id=floor_id,
                    building_id=building_id,
                    area_id=area_id,
                )
                for row in rows
            ])
        except ValueError as exc:
            return ApiResponse.error(ErrorCode.PARSE_ERROR, str(exc))

    async def query_electricity(
        self,
        *,
        area_id: str,
        building_id: str,
        floor_id: str,
        room_id: str,
        room_name: str | None = None,
    ) -> ApiResponse[ElectricityReading]:
        invalid = _require_ids(area_id=area_id, building_id=building_id, floor_id=floor_id, room_id=room_id)
        if invalid:
            return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, invalid)
        result = await self._post_business_api(
            "search",
            {"areaid": area_id, "partmentId": building_id, "floorId": floor_id, "dromNumber": room_id},
        )
        if not result.success:
            return _pass_error(result)
        if not isinstance(result.data, dict):
            return ApiResponse.error(ErrorCode.PARSE_ERROR, "/search response data is not an object")
        data = result.data
        price = _optional_float(data.get("price"))
        surplus = _optional_float(data.get("surplus"))
        free_end = _optional_float(data.get("freeEnd"))
        if area_id == "1":
            reading = ElectricityReading(
                area_id=area_id,
                building_id=building_id,
                building_name=_optional_string(data.get("parName")),
                floor_id=floor_id,
                floor_name=_optional_string(data.get("floorName")),
                room_id=room_id,
                room_name=room_name,
                source_time=_optional_string(data.get("time")),
                remaining_energy_kwh=surplus,
                free_remaining_kwh=free_end,
                price_per_kwh=price,
                raw_data=data,
            )
        else:
            remaining_kwh = surplus / price if surplus is not None and price is not None and price > 0 else None
            reading = ElectricityReading(
                area_id=area_id,
                building_id=building_id,
                building_name=_optional_string(data.get("parName")),
                floor_id=floor_id,
                floor_name=_optional_string(data.get("floorName")),
                room_id=room_id,
                room_name=room_name,
                source_time=_optional_string(data.get("time")),
                remaining_money=surplus,
                remaining_kwh=remaining_kwh,
                total_usage_kwh=free_end,
                price_per_kwh=price,
                raw_data=data,
            )
        return ApiResponse.ok(reading)

    async def _post_business_api(self, endpoint: str, data: dict[str, str]) -> ApiResponse[Any]:
        """Post one confirmed form endpoint and normalize upstream/session failures."""
        url = f"{BASE_URL}{BUSINESS_PREFIX}/{endpoint}"
        try:
            response = await self._send("POST", url, stage=f"POST /{endpoint}", data=data)
        except AuthFailure as exc:
            return ApiResponse.error(_auth_error_code(exc), "network request failed")

        location = response.headers.get("location", "")
        if response.is_redirect:
            if "/uc/wap/login" in location:
                return ApiResponse.error(ErrorCode.SESSION_EXPIRED, "app session expired")
            return ApiResponse.error(ErrorCode.UPSTREAM_ERROR, f"unexpected redirect from /{endpoint}")
        if response.status_code != 200:
            return ApiResponse.error(ErrorCode.UPSTREAM_ERROR, f"upstream returned HTTP {response.status_code}")
        if "用户信息已失效" in response.text:
            return ApiResponse.error(ErrorCode.SESSION_EXPIRED, "app session expired")
        try:
            payload = response.json()
        except ValueError:
            return ApiResponse.error(ErrorCode.PARSE_ERROR, f"/{endpoint} response was not JSON")
        if not isinstance(payload, dict):
            return ApiResponse.error(ErrorCode.PARSE_ERROR, f"/{endpoint} response was not an object")
        if str(payload.get("e")) != "0":
            message = _optional_string(payload.get("m")) or f"/{endpoint} returned a business error"
            return ApiResponse.error(ErrorCode.BUSINESS_ERROR, message)
        container = payload.get("d")
        if not isinstance(container, dict):
            return ApiResponse.error(ErrorCode.PARSE_ERROR, f"/{endpoint} response missing object d")
        if "data" not in container:
            return ApiResponse.error(ErrorCode.PARSE_ERROR, f"/{endpoint} response missing d.data")
        return ApiResponse.ok(container["data"], _optional_string(payload.get("m")) or "操作成功")


def _pass_error(result: ApiResponse[Any]) -> ApiResponse[Any]:
    return ApiResponse.error(result.code, result.message)


def _auth_error_code(error: AuthFailure) -> ErrorCode:
    if error.kind == AuthErrorKind.TIMEOUT:
        return ErrorCode.TIMEOUT
    if error.kind == AuthErrorKind.NETWORK_ERROR:
        return ErrorCode.NETWORK_ERROR
    return ErrorCode.UPSTREAM_ERROR


def _require_ids(**values: str) -> str | None:
    for name, value in values.items():
        if not isinstance(value, str) or not value.strip():
            return f"{name} must be a non-empty string"
    return None


def _as_list(value: Any) -> list[Mapping[str, Any]] | None:
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        return None
    return value


def _required_string(row: Mapping[str, Any], key: str) -> str:
    value = _optional_string(row.get(key))
    if value is None:
        raise ValueError(f"response item missing {key}")
    return value


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _optional_float(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
