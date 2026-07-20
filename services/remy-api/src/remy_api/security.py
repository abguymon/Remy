"""Password hashing, JWT issuance/verification, and API-token helpers.

* Passwords: argon2id via ``argon2-cffi`` (memory-hard, modern default).
* Web auth: JWT HS256, 7-day expiry, ``sub`` = user id, signed with ``JWT_SECRET``.
* MCP auth: opaque bearer tokens prefixed ``remy_``; only their SHA-256 hash is
  stored (FR-26). The prefix lets :mod:`remy_api.deps` route a bearer token to
  the right verification path without a DB probe.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from remy_api.config import get_settings
from remy_api.errors import AuthenticationError

API_TOKEN_PREFIX = "remy_"
_ph = PasswordHasher()


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # malformed hash — treat as non-match, never crash auth
        return False


# --- JWT (web) ---------------------------------------------------------------


def create_access_token(user_id: str, auth_version: int = 0) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "av": auth_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_expire_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> tuple[str, int]:
    """Return the user id and session version from a valid token, else raise 401."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc
    sub = payload.get("sub")
    auth_version = payload.get("av", 0)
    if not sub or not isinstance(auth_version, int):
        raise AuthenticationError("Invalid authentication token.")
    return str(sub), auth_version


# --- Invitations ------------------------------------------------------------


def generate_invitation_token() -> tuple[str, str]:
    """Return a high-entropy invitation capability and its stored digest."""
    token = secrets.token_urlsafe(32)
    return token, hash_invitation_token(token)


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- API tokens (MCP) --------------------------------------------------------


def generate_api_token() -> tuple[str, str]:
    """Return ``(full_token, sha256_hash)``. The full token is shown once."""
    full = f"{API_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    return full, hash_api_token(full)


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def looks_like_api_token(token: str) -> bool:
    return token.startswith(API_TOKEN_PREFIX)
