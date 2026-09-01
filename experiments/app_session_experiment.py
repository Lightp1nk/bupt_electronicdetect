"""Isolated app.bupt.edu.cn business-cookie experiment; never use in production."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import re
import sys
from http.cookiejar import Cookie
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.providers.bupt_auth import AuthFailure  # noqa: E402
from app.providers.bupt_client import BUPTClient  # noqa: E402

PART_URL = "https://app.bupt.edu.cn/buptdf/wap/default/part"
SESSION_FILE = Path(__file__).with_name(".runtime_app_session.json")
APP_HOST = "app.bupt.edu.cn"


def is_app_cookie(cookie: Cookie) -> bool:
    return cookie.domain.lstrip(".") == APP_HOST


def safe_metadata(cookies: list[Cookie]) -> list[dict[str, object]]:
    return [{"name": c.name, "domain": c.domain, "path": c.path, "secure": c.secure, "has_expires": c.expires is not None} for c in cookies]


def serialize(cookies: list[Cookie]) -> list[dict[str, object]]:
    return [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path, "expires": c.expires, "secure": c.secure, "discard": c.discard, "domain_specified": c.domain_specified, "domain_initial_dot": c.domain_initial_dot, "path_specified": c.path_specified} for c in cookies]


def deserialize(rows: list[dict[str, object]]) -> list[Cookie]:
    return [Cookie(version=0, name=str(r["name"]), value=str(r["value"]), port=None, port_specified=False, domain=str(r["domain"]), domain_specified=bool(r["domain_specified"]), domain_initial_dot=bool(r["domain_initial_dot"]), path=str(r["path"]), path_specified=bool(r["path_specified"]), secure=bool(r["secure"]), expires=r["expires"] if isinstance(r["expires"], int) else None, discard=bool(r["discard"]), comment=None, comment_url=None, rest={}, rfc2109=False) for r in rows]


def install(client: httpx.AsyncClient, cookies: list[Cookie]) -> None:
    for cookie in cookies:
        client.cookies.jar.set_cookie(cookie)


def safe_trace(message: str) -> None:
    """Keep bootstrap diagnostics within the experiment log whitelist."""
    status = re.match(r"^\[(\d{3})\]", message)
    if " -> " in message:
        target = urlsplit(message.rsplit(" -> ", maxsplit=1)[1])
        print(
            "bootstrap_redirect: "
            f"http_status={status.group(1) if status else '-'}; "
            f"redirect_host={target.hostname or '-'}; redirect_path={target.path}"
        )
    elif status:
        print(f"bootstrap_response: http_status={status.group(1)}")
    else:
        print("bootstrap_step")


async def verify(client: httpx.AsyncClient, label: str) -> bool:
    try:
        response = await client.post(PART_URL, data={"areaid": "1"}, follow_redirects=False)
        host = urlsplit(response.headers.get("location", "")).hostname or "-"
        ok = response.status_code == 200 and isinstance(response.json(), dict) and str(response.json().get("e")) == "0"
        print(f"{label}: {'success' if ok else 'failed'}")
        print(f"http_status: {response.status_code}; redirect_host: {host}; expected_json: {ok}")
        return ok
    except (httpx.RequestError, ValueError):
        print(f"{label}: failed")
        print("http_status: unavailable; redirect_host: -; expected_json: false")
        return False


async def bootstrap() -> int:
    username, password = input("BUPT username: "), getpass.getpass("BUPT password: ")
    try:
        async with BUPTClient(trace=safe_trace) as bootstrap_client:
            await bootstrap_client.login(username, password)
            app_cookies = [c for c in bootstrap_client.client.cookies.jar if is_app_cookie(c)]
            print("app_cookie_metadata:", safe_metadata(app_cookies))
            async with httpx.AsyncClient(timeout=20) as runtime:
                install(runtime, app_cookies)
                h1 = await verify(runtime, "runtime_app_cookie_only")
                # The bootstrap client remains separate; close it before the second isolated request.
            serialized = serialize(app_cookies)
        if not h1:
            print("H1: NOT_SUPPORTED; stopping before cross-process experiment")
            return 1
        async with httpx.AsyncClient(timeout=20) as runtime:
            install(runtime, deserialize(serialized))
            h1b = await verify(runtime, "runtime_isolated_client")
        if not h1b:
            print("H1: NOT_SUPPORTED; stopping before cross-process experiment")
            return 1
        SESSION_FILE.write_text(json.dumps(serialized), encoding="utf-8")
        try: os.chmod(SESSION_FILE, 0o600)
        except OSError: pass
        print("H1: VERIFIED; bootstrap client closed; run: python experiments/app_session_experiment.py restore")
        return 0
    except AuthFailure as exc:
        print(f"bootstrap_login: failed ({exc.kind.value})")
        return 1
    except Exception:
        print("bootstrap_login: failed (unexpected)")
        return 1


async def restore() -> int:
    if not SESSION_FILE.exists(): print("cross_process_restore: failed (temporary session file missing)"); return 1
    try:
        rows = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        cookies = deserialize(rows)
        async with httpx.AsyncClient(timeout=20) as runtime:
            install(runtime, cookies)
            before = {(c.name, c.domain, c.path): (c.value, c.expires) for c in runtime.cookies.jar if is_app_cookie(c)}
            ok = await verify(runtime, "cross_process_restore")
            after = {(c.name, c.domain, c.path): (c.value, c.expires) for c in runtime.cookies.jar if is_app_cookie(c)}
            print("session_rotation_detected:", any(before.get(k) != v for k, v in after.items()) or set(before) != set(after))
            for key in sorted(set(before) | set(after)):
                print(f"cookie_rotation {key[0]}: value_changed={before.get(key, (None, None))[0] != after.get(key, (None, None))[0]}; expires_changed={before.get(key, (None, None))[1] != after.get(key, (None, None))[1]}")
        return 0 if ok else 1
    except Exception:
        print("cross_process_restore: failed (unexpected)")
        return 1
    finally:
        SESSION_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("bootstrap", "restore")); args = parser.parse_args()
    raise SystemExit(asyncio.run(bootstrap() if args.mode == "bootstrap" else restore()))
