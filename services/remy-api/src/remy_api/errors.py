"""Typed errors and a consistent error response shape (PRD §9.1).

Every failure returns ``{"error": {"code": ..., "message": ...}}`` with the
right status (401 vs 403 vs 404 vs 409 vs 422). No silent empty successes.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class APIError(Exception):
    """Base application error carrying an HTTP status and a stable code."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class AuthenticationError(APIError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"


class PermissionError_(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(APIError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class RateLimitError(APIError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class UnprocessableError(APIError):
    """A well-formed request that violates a business rule (422)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "unprocessable"


def _payload(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    """Install exception handlers producing the uniform error envelope."""

    @app.exception_handler(APIError)
    async def _handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == status.HTTP_401_UNAUTHORIZED else None
        payload = _payload(exc.code, exc.message)
        # Some errors (recipe-parse, upload-rejected) carry machine-readable
        # ``reasons`` explaining *why* they failed; surface them (PRD §9.1).
        reasons = getattr(exc, "reasons", None)
        if reasons:
            payload["error"]["reasons"] = list(reasons)
        return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthenticated",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
        }.get(exc.status_code, "error")
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(status_code=exc.status_code, content=_payload(code, detail))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=jsonable_encoder(
                {"error": {"code": "validation_error", "message": "Invalid request.", "details": exc.errors()}}
            ),
        )
