"""Shared interactive campus/building/floor/room selection for local probes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from app.providers.bupt_client import BUPTClient
from app.schemas.common import ApiResponse, ErrorCode
from app.schemas.dormitory import Building, Floor, Room


CAMPUSES = {"1": "西土城", "2": "沙河"}
T = TypeVar("T")


@dataclass(frozen=True)
class DormitorySelection:
    area_id: str
    building: Building
    floor: Floor
    room: Room


def choose(prompt: str, items: list[T]) -> T:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("Please enter a listed number.")


async def select_dormitory(client: BUPTClient) -> ApiResponse[DormitorySelection]:
    print("\nChoose campus:\n[1] 西土城\n[2] 沙河")
    area_id = input("Campus: ").strip()
    if area_id not in CAMPUSES:
        return ApiResponse.error(ErrorCode.INVALID_ARGUMENT, "invalid campus")
    buildings = await client.get_buildings(area_id=area_id)
    if not buildings.success or not buildings.data:
        return ApiResponse.error(buildings.code, buildings.message)
    for index, building in enumerate(buildings.data, 1):
        print(f"[{index}] {building.name}")
    building = choose("Building: ", buildings.data)
    floors = await client.get_floors(area_id=area_id, building_id=building.id)
    if not floors.success or not floors.data:
        return ApiResponse.error(floors.code, floors.message)
    for index, floor in enumerate(floors.data, 1):
        print(f"[{index}] {floor.name}")
    floor = choose("Floor: ", floors.data)
    rooms = await client.get_rooms(area_id=area_id, building_id=building.id, floor_id=floor.id)
    if not rooms.success or not rooms.data:
        return ApiResponse.error(rooms.code, rooms.message)
    for index, room in enumerate(rooms.data, 1):
        print(f"[{index}] {room.name}")
    room = choose("Room: ", rooms.data)
    return ApiResponse.ok(DormitorySelection(area_id, building, floor, room))
