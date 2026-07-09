"""MCP facade (PRD §7.4): a second, agent-facing interface for Remy.

``remy-api`` mounts a FastMCP server at ``/mcp`` (streamable-HTTP transport,
stateless) when ``MCP_FACADE_ENABLED`` is set (default on). It exposes coarse
tools mirroring the pipeline gates and calls the same ``planner``/``recipes``/
``kroger`` modules the web app uses — one workflow implementation, no divergence.

Library choice: the official ``mcp`` Python SDK's ``FastMCP`` (already a
transitive dependency). Its ``streamable_http_app()`` is a Starlette ASGI app
that mounts cleanly into the existing FastAPI app; a thin ASGI auth middleware
enforces per-request bearer API-token auth. We use streamable-HTTP (the current
MCP transport) rather than the deprecated SSE transport.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import FastAPI

from remy_api.mcp_facade.auth import MCPAuthMiddleware
from remy_api.mcp_facade.tools import build_mcp_server

logger = logging.getLogger("remy.mcp")

MCP_MOUNT_PATH = "/mcp"

__all__ = ["MCP_MOUNT_PATH", "attach_mcp_if_enabled", "build_mcp_server", "mount_mcp"]


def attach_mcp_if_enabled(app: FastAPI, settings) -> contextlib.AbstractAsyncContextManager | None:  # noqa: ANN001
    """Mount the facade iff ``settings.mcp_facade_enabled`` (PRD §8 feature flag).

    Returns the session-manager lifespan context to enter (or ``None`` when the
    flag is off, in which case ``/mcp`` is never mounted).
    """
    if not settings.mcp_facade_enabled:
        logger.info("MCP facade disabled (MCP_FACADE_ENABLED=false); /mcp not mounted")
        return None
    return mount_mcp(app)


def mount_mcp(app: FastAPI) -> contextlib.AbstractAsyncContextManager | None:
    """Mount the MCP endpoint at ``/mcp`` and return its lifespan context.

    Returns an async context manager that runs the FastMCP session manager (the
    app's lifespan must enter it), or ``None`` if nothing was mounted. Call under
    the ``MCP_FACADE_ENABLED`` flag only.
    """
    mcp = build_mcp_server()
    # streamable_http_path="/" so the sub-app's route is "/" and the mount makes
    # the effective endpoint exactly ``/mcp``.
    asgi_app = mcp.streamable_http_app()
    app.mount(MCP_MOUNT_PATH, MCPAuthMiddleware(asgi_app))
    logger.info("MCP facade mounted at %s (streamable-http)", MCP_MOUNT_PATH)

    @contextlib.asynccontextmanager
    async def _session_manager_lifespan() -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    return _session_manager_lifespan()
