"""Run the minimal BUPT CAS authentication and /part verification probe."""

from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.bupt_auth import AuthFailure, BUPTAuthClient


def prompt_credentials() -> tuple[str, str]:
    """Called only after authserver has actually returned a login page."""
    return input("BUPT username: "), getpass.getpass("BUPT password: ")


async def main() -> int:
    try:
        async with BUPTAuthClient(credential_provider=prompt_credentials, trace=print) as auth:
            result = await auth.login()
            print("[OK] chong returned 200")
            print("[OK] /part returned e=0")
            print("Cookie names:")
            for name in result.cookie_names:
                print(f"- {name}: present")
            print("AUTHENTICATION SUCCESS")
            return 0
    except AuthFailure as exc:
        print(f"AUTHENTICATION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
