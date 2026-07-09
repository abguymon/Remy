"""Map the Kroger error hierarchy onto the uniform API error envelope (§9.1).

Registered from ``main.py`` so any :class:`KrogerError` escaping an endpoint
becomes a truthful ``{"error": {"code", "message"}}`` response rather than a
generic 500. Kept separate from ``errors.py`` (T1) to avoid coupling the
integration layer to the app-error module.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .errors import (
    KrogerAPIError,
    KrogerAuthError,
    KrogerError,
    KrogerNotConnectedError,
    KrogerRateLimitError,
)


def _status_and_code(exc: KrogerError) -> tuple[int, str]:
    if isinstance(exc, KrogerNotConnectedError):
        return status.HTTP_409_CONFLICT, "kroger_not_connected"
    if isinstance(exc, KrogerRateLimitError):
        return status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited"
    if isinstance(exc, KrogerAuthError):
        return status.HTTP_502_BAD_GATEWAY, "kroger_auth_error"
    if isinstance(exc, KrogerAPIError):
        return status.HTTP_502_BAD_GATEWAY, "kroger_api_error"
    return status.HTTP_502_BAD_GATEWAY, "kroger_error"


def register_kroger_error_handler(app: FastAPI) -> None:
    @app.exception_handler(KrogerError)
    async def _handle_kroger_error(_request: Request, exc: KrogerError) -> JSONResponse:
        status_code, code = _status_and_code(exc)
        headers = None
        if isinstance(exc, KrogerRateLimitError) and exc.retry_after is not None:
            headers = {"Retry-After": str(exc.retry_after)}
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": code, "message": exc.message}},
            headers=headers,
        )
