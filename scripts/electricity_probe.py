"""Interactive, single-room BUPT electricity query probe."""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.bupt_auth import AuthFailure
from app.providers.bupt_client import BUPTClient
from app.schemas.common import ApiResponse


CAMPUSES = {"1": "西土城", "2": "沙河"}


def prompt_credentials() -> tuple[str, str]:
    return input("BUPT username: "), getpass.getpass("BUPT password: ")


def choose(prompt: str, items: list[object]) -> object:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("Please enter a listed number.")


def show_error(result: ApiResponse[object]) -> None:
    print(f"Request failed: {result.code.value} — {result.message}", file=sys.stderr)


def display_reading(campus: str, building: object, floor: object, room: object, reading: object) -> None:
    print("\nQuery successful\n")
    print(f"Campus: {campus}")
    print(f"Building: {getattr(building, 'name')}")
    print(f"Floor: {getattr(floor, 'name')}")
    print(f"Room: {getattr(room, 'name')}")
    print(f"\nSource time: {getattr(reading, 'source_time') or 'N/A'}")
    value = getattr(reading, "remaining_money")
    if value is not None:
        print(f"Remaining money: {value:.2f} yuan")
    value = getattr(reading, "price_per_kwh")
    if value is not None:
        print(f"Price: {value:.2f} yuan/kWh")
    value = getattr(reading, "remaining_kwh")
    if value is not None:
        print(f"Estimated remaining electricity: {value:.2f} kWh")
    value = getattr(reading, "total_usage_kwh")
    if value is not None:
        print(f"Total usage: {value:.2f} kWh")
    value = getattr(reading, "remaining_energy_kwh")
    if value is not None:
        print(f"Remaining energy: {value:.2f} kWh")
    value = getattr(reading, "free_remaining_kwh")
    if value is not None:
        print(f"Remaining free energy: {value:.2f} kWh")


async def main() -> int:
    try:
        async with BUPTClient(credential_provider=prompt_credentials, trace=print) as client:
            await client.login()
            print("\nChoose campus:\n[1] 西土城\n[2] 沙河")
            area_id = input("Campus: ").strip()
            if area_id not in CAMPUSES:
                print("Invalid campus.", file=sys.stderr)
                return 1

            buildings = await client.get_buildings(area_id=area_id)
            if not buildings.success or not buildings.data:
                show_error(buildings)
                return 1
            for index, building in enumerate(buildings.data, 1):
                print(f"[{index}] {building.name}")
            building = choose("Building: ", buildings.data)

            floors = await client.get_floors(area_id=area_id, building_id=building.id)
            if not floors.success or not floors.data:
                show_error(floors)
                return 1
            for index, floor in enumerate(floors.data, 1):
                print(f"[{index}] {floor.name}")
            floor = choose("Floor: ", floors.data)

            rooms = await client.get_rooms(area_id=area_id, building_id=building.id, floor_id=floor.id)
            if not rooms.success or not rooms.data:
                show_error(rooms)
                return 1
            for index, room in enumerate(rooms.data, 1):
                print(f"[{index}] {room.name}")
            room = choose("Room: ", rooms.data)

            reading = await client.query_electricity(
                area_id=area_id,
                building_id=building.id,
                floor_id=floor.id,
                room_id=room.id,
                room_name=room.name,
            )
            if not reading.success or reading.data is None:
                show_error(reading)
                return 1
            display_reading(CAMPUSES[area_id], building, floor, room, reading.data)
            return 0
    except AuthFailure as exc:
        print(f"AUTHENTICATION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
