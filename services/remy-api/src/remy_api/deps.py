"""Authentication dependency shared by the web app and the MCP facade.

``get_current_user`` accepts a single ``Authorization: Bearer <token>`` header
and supports BOTH auth paths (FR-26):

* ``remy_``-prefixed tokens → API tokens: looked up by SHA-256 hash, must not be
  revoked; ``last_used_at`` is stamped on every successful use.
* everything else → a JWT: decoded, ``sub`` resolved to a user.

Both resolve to the same :class:`User`, giving MCP clients the same ``user_id``
scoping as the web session. Failures raise typed 401/403 errors (never silent).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.db import get_session
from remy_api.errors import AuthenticationError, PermissionError_
from remy_api.models import ApiToken, User
from remy_api.observability import bind_observation_context
from remy_api.security import decode_access_token, hash_api_token, looks_like_api_token

# auto_error=False so a missing header yields our typed 401, not FastAPI's 403.
_bearer = HTTPBearer(auto_error=False)


async def _user_from_api_token(session: AsyncSession, token: str) -> User:
    token_hash = hash_api_token(token)
    row = await session.execute(select(ApiToken).where(ApiToken.token_hash == token_hash))
    api_token = row.scalar_one_or_none()
    if api_token is None or api_token.revoked_at is not None:
        raise AuthenticationError("Invalid or revoked API token.")
    api_token.last_used_at = datetime.now(UTC)
    user = await session.get(User, api_token.user_id)
    if user is None:
        raise AuthenticationError("Token owner no longer exists.")
    await session.commit()
    return user


async def _user_from_jwt(session: AsyncSession, token: str) -> User:
    user_id, auth_version = decode_access_token(token)
    user = await session.get(User, user_id)
    if user is None:
        raise AuthenticationError("User no longer exists.")
    if user.auth_version != auth_version:
        raise AuthenticationError("Your session has been invalidated. Please sign in again.")
    return user


async def resolve_bearer_user(session: AsyncSession, token: str) -> User:
    """Resolve a bearer token (API token or JWT) to an active :class:`User`.

    The single source of truth for bearer auth, shared by the HTTP dependency
    below and the MCP facade middleware so the two interfaces resolve identical
    ``user_id`` scoping (no duplicated hash lookup, FR-26 / PRD §7.4).
    """
    if looks_like_api_token(token):
        user = await _user_from_api_token(session, token)
    else:
        user = await _user_from_jwt(session, token)
    if not user.is_active:
        raise PermissionError_("User account is disabled.")
    return user


async def resolve_api_token_user(session: AsyncSession, token: str) -> User:
    """Resolve an *API token only* (``remy_`` prefix) to an active user.

    The MCP facade rejects JWTs and anything else: agents authenticate solely
    with Settings-generated API tokens (PRD §7.4).
    """
    if not looks_like_api_token(token):
        raise AuthenticationError("MCP requires a Remy API token (starts with 'remy_'). Generate one in Settings.")
    user = await _user_from_api_token(session, token)
    if not user.is_active:
        raise PermissionError_("User account is disabled.")
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncIterator[User]:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token.")
    user = await resolve_bearer_user(session, credentials.credentials)
    with bind_observation_context(user_id=user.id):
        yield user


CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def require_admin(user: CurrentUser) -> User:
    """Gate a route on the caller being an administrator (403 otherwise)."""
    if not user.is_admin:
        raise PermissionError_("Administrator access required.", code="admin_required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
