"""Verify one FastAPI login supports repeated protected requests without re-entering credentials."""

from __future__ import annotations

import argparse
import asyncio
import getpass

import httpx


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    username = input("BUPT username: ")
    password = getpass.getpass("BUPT password: ")
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0) as client:
        login = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
        if not _ok(login, "login"):
            return 1
        status = await client.get("/api/v1/auth/status")
        if not _ok(status, "status after login"):
            return 1
        area_id = input("Campus [1 西土城 / 2 沙河]: ").strip()
        if area_id not in {"1", "2"}:
            print("Invalid campus.")
            return 1
        for attempt in (1, 2):
            buildings = await client.get("/api/v1/electricity/buildings", params={"area_id": area_id})
            if not _ok(buildings, f"business request {attempt}"):
                return 1
            print(f"Business request {attempt}: reused active server session.")
        status = await client.get("/api/v1/auth/status")
        if not _ok(status, "status after repeated business requests"):
            return 1
        logout = await client.post("/api/v1/auth/logout")
        if not _ok(logout, "logout"):
            return 1
        final_status = await client.get("/api/v1/auth/status")
        if not _ok(final_status, "status after logout"):
            return 1
        protected = await client.get("/api/v1/electricity/buildings", params={"area_id": area_id})
        body = protected.json()
        if protected.status_code != 401 or body.get("code") != "AUTH_REQUIRED":
            print("Protected endpoint did not return AUTH_REQUIRED after logout.")
            return 1
    print("SESSION PROBE SUCCESS")
    return 0


def _ok(response: httpx.Response, stage: str) -> bool:
    try:
        payload = response.json()
    except ValueError:
        print(f"{stage} failed: non-JSON response")
        return False
    if response.status_code != 200 or not payload.get("success"):
        print(f"{stage} failed: {payload.get('code', 'UNKNOWN')}")
        return False
    print(f"{stage}: OK")
    return True


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
