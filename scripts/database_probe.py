"""Interactively query one room, save its electricity snapshot, and show history count."""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.database import SessionLocal, dispose_db, init_db
from app.providers.bupt_auth import AuthFailure
from app.providers.bupt_client import BUPTClient
from app.services.electricity_service import ElectricityService
from interactive_selection import select_dormitory


def prompt_credentials() -> tuple[str, str]:
    return input("BUPT username: "), getpass.getpass("BUPT password: ")


async def main() -> int:
    await init_db()
    try:
        async with BUPTClient(credential_provider=prompt_credentials, trace=print) as client:
            await client.login()
            selected = await select_dormitory(client)
            if not selected.success or selected.data is None:
                print(f"Selection failed: {selected.code.value}", file=sys.stderr)
                return 1
            item = selected.data
            async with SessionLocal() as session:
                service = ElectricityService(session)
                result = await service.query_and_save(
                    client,
                    area_id=item.area_id,
                    building_id=item.building.id,
                    floor_id=item.floor.id,
                    room_id=item.room.id,
                    room_name=item.room.name,
                )
                if not result.success or result.data is None:
                    print(f"Query failed: {result.code.value}", file=sys.stderr)
                    return 1
                print("Query success")
                print("Database save success" if result.data.saved else "Duplicate snapshot, skipped insert")
                history = await service.get_history(area_id=item.area_id, room_id=item.room.id)
                if not history.success or history.data is None:
                    print(f"History read failed: {history.code.value}", file=sys.stderr)
                    return 1
                print(f"History count: {len(history.data)}")
                return 0
    except AuthFailure as exc:
        print(f"AUTHENTICATION FAILED: {exc}", file=sys.stderr)
        return 1
    finally:
        await dispose_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
