"""Token generation, hashing, and expiry policy for local browser sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import os
import secrets


SESSION_COOKIE_NAME = "bupt_electricity_session"


@dataclass(frozen=True)
class AppSessionConfig:
    ttl: timedelta = timedelta(days=14)
    secure_cookie: bool = False
    last_seen_interval: timedelta = timedelta(minutes=5)

    @classmethod
    def from_environment(cls) -> "AppSessionConfig":
        ttl_hours = int(os.getenv("APP_SESSION_TTL_HOURS", str(14 * 24)))
        last_seen_seconds = int(os.getenv("APP_SESSION_LAST_SEEN_INTERVAL_SECONDS", "300"))
        secure_cookie = os.getenv("APP_SESSION_COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
        if ttl_hours <= 0 or last_seen_seconds < 0:
            raise ValueError("app session lifetime settings must be non-negative and non-zero")
        return cls(timedelta(hours=ttl_hours), secure_cookie, timedelta(seconds=last_seen_seconds))


def utc_now() -> datetime:
    """Store UTC as a naive value, matching this SQLite project's datetime convention."""
    return datetime.now(UTC).replace(tzinfo=None)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
