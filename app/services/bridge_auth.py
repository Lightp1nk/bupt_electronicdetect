"""Authentication for trusted AstrBot Bridge callbacks."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


def require_astrbot_bridge(authorization: str | None = Header(default=None)) -> None:
    """Accept only the bridge bearer token, without logging its value."""
    expected = os.getenv("ASTRBOT_BRIDGE_TOKEN")
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Bridge validation is unavailable")

    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bridge authentication failed")
