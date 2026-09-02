"""Authentication for AstrBot-to-FastAPI internal APIs."""

from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


def require_astrbot_internal(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("ASTRBOT_INTERNAL_TOKEN")
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AstrBot internal API is unavailable")
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="internal API authentication failed")
