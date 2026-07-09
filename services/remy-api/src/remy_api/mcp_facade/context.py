"""Per-request user context + shared helpers for the MCP facade (T6).

The auth middleware (:mod:`remy_api.mcp_facade.auth`) resolves the bearer API
token to a ``user_id`` and stashes it in a :class:`contextvars.ContextVar` before
the MCP protocol handler runs; tool functions read it back through
:func:`tool_context`. Context variables copy into the child tasks the streamable
transport spawns, so the value set on the request task is visible inside the tool.
Tests set the context directly via :func:`use_user`.

Every tool call opens its own :class:`AsyncSession` (mirroring the FastAPI
``get_session`` dependency) and loads the :class:`User`, so tools call the exact
same ``planner``/``recipes``/``kroger`` functions the web app does — no divergent
logic (PRD §4, §7.4).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from remy_api.db import get_session_factory
from remy_api.models import User
from remy_api.planner import machine
from remy_api.planner.schemas import PlanSnapshot

# Set by the auth middleware per request; read by tools. Default None = no auth
# resolved (a tool called outside an authenticated request raises).
_current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("remy_mcp_user_id", default=None)


class MCPAuthError(Exception):
    """Raised inside a tool when no authenticated user is in context."""


def set_current_user_id(user_id: str | None) -> contextvars.Token:
    return _current_user_id.set(user_id)


def reset_current_user_id(token: contextvars.Token) -> None:
    _current_user_id.reset(token)


@contextlib.contextmanager
def use_user(user_id: str):
    """Bind ``user_id`` for the duration of the block (used by tests)."""
    token = _current_user_id.set(user_id)
    try:
        yield
    finally:
        _current_user_id.reset(token)


def current_user_id() -> str:
    user_id = _current_user_id.get()
    if not user_id:
        raise MCPAuthError("No authenticated user in context. This tool requires an MCP bearer API token.")
    return user_id


@contextlib.asynccontextmanager
async def tool_context() -> AsyncIterator[tuple[AsyncSession, User]]:
    """Yield ``(session, user)`` for the current authenticated MCP request."""
    user_id = current_user_id()
    factory = get_session_factory()
    async with factory() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise MCPAuthError("Authenticated user no longer exists or is disabled.")
        yield session, user


async def wait_for_step(user_id: str, timeout: float = 120.0) -> bool:
    """Wait for the user's in-flight background step (discover/match) to finish.

    Agents are poor at polling, so the async tools block here until the step
    completes and return a full result in one call. Returns ``True`` if the step
    finished within ``timeout``, ``False`` on timeout (the caller then returns
    the progress-so-far snapshot plus retry guidance; the background task keeps
    running and ``plan_status`` remains available for resumption).
    """
    try:
        await asyncio.wait_for(machine.drain(user_id), timeout=timeout)
        return True
    except (TimeoutError, asyncio.TimeoutError):  # noqa: UP041 - be explicit across versions
        return False


async def load_snapshot(session: AsyncSession, user_id: str) -> PlanSnapshot | None:
    plan = await machine.get_active_plan(session, user_id)
    if plan is None:
        return None
    return machine.snapshot(plan)
