"""Small in-process throttle for public credential endpoints."""

from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic

from fastapi import Request

from remy_api.config import get_settings
from remy_api.errors import RateLimitError

_attempts: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    # nginx appends the real peer address to X-Forwarded-For; take its rightmost
    # entry rather than trusting an attacker-controlled leading value.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.rsplit(",", 1)[-1].strip()
    return request.client.host if request.client else "unknown"


def _check(request: Request, scope: str, limit: int) -> None:
    now = monotonic()
    window = get_settings().auth_rate_limit_window_seconds
    key = f"{scope}:{_client_key(request)}"
    entries = _attempts[key]
    while entries and entries[0] <= now - window:
        entries.popleft()
    if len(entries) >= limit:
        raise RateLimitError("Too many attempts. Please wait and try again.")
    entries.append(now)


def check_login_rate_limit(request: Request) -> None:
    _check(request, "login", get_settings().auth_login_rate_limit)


def check_registration_rate_limit(request: Request) -> None:
    _check(request, "register", get_settings().auth_registration_rate_limit)


def reset_rate_limits() -> None:
    """Clear process state for tests."""
    _attempts.clear()
