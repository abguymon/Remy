"""Bearer-token auth for the mounted MCP endpoint (PRD §7.4).

A pure-ASGI middleware wrapping the FastMCP streamable-HTTP app. Every request
must carry ``Authorization: Bearer remy_...``; the token is resolved to a
:class:`User` via the *same* hash lookup the web app uses
(:func:`remy_api.deps.resolve_api_token_user`) and the resolved ``user_id`` is
bound into the request context so tools are scoped to that user. Anything
missing, malformed, a JWT, or a revoked/unknown token is rejected with a JSON
error before the MCP protocol handler runs.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from remy_api.db import get_session_factory
from remy_api.deps import resolve_api_token_user
from remy_api.errors import APIError
from remy_api.mcp_facade.context import reset_current_user_id, set_current_user_id
from remy_api.observability import bind_observation_context

Scope = dict
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]


def _extract_bearer(scope: Scope) -> str | None:
    for key, value in scope.get("headers", []):
        if key == b"authorization":
            raw = value.decode("latin-1")
            if raw.lower().startswith("bearer "):
                return raw[7:].strip()
            return None
    return None


async def _send_error(send: Send, status_code: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message}}).encode()
    headers = [(b"content-type", b"application/json")]
    if status_code == 401:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class MCPAuthMiddleware:
    """Authenticate every MCP HTTP request, then bind the user into context."""

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _extract_bearer(scope)
        if not token:
            await _send_error(send, 401, "unauthenticated", "Missing bearer token. MCP requires a Remy API token.")
            return

        factory = get_session_factory()
        try:
            async with factory() as session:
                user = await resolve_api_token_user(session, token)
                user_id = user.id
        except APIError as exc:
            await _send_error(send, exc.status_code, exc.code, exc.message)
            return

        ctx_token = set_current_user_id(user_id)
        try:
            with bind_observation_context(user_id=user_id):
                await self.app(scope, receive, send)
        finally:
            reset_current_user_id(ctx_token)
