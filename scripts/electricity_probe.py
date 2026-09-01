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
from interactive_selection import CAMPUSES, select_dormitory


def prompt_credentials() -> tuple[str, str]:
    return input("BUPT username: "), getpass.getpass("BUPT password: ")


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
            selected = await select_dormitory(client)
            if not selected.success or selected.data is None:
                show_error(selected)
                return 1
            area_id = selected.data.area_id
            building = selected.data.building
            floor = selected.data.floor
            room = selected.data.room

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
