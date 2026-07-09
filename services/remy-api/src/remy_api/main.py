"""Remy v2 API entrypoint.

Validates configuration fail-closed at import time (so a misconfigured
deployment fails immediately rather than serving broken endpoints), creates the
database schema on startup, and mounts the auth/user routers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from remy_api import __version__
from remy_api.config import get_settings
from remy_api.db import dispose_engine, init_db
from remy_api.errors import register_error_handlers
from remy_api.kroger import close_client, register_kroger_error_handler
from remy_api.llm.errors import LLMError
from remy_api.routers import auth, kroger, plan, recipes, users
from remy_api.search.base import SearchError

# Fail closed: importing the app validates required secrets. A misconfigured
# container exits here with a clear ConfigError rather than starting.
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # No Alembic in v1; create tables on startup (models are kept clean enough
    # to add migrations later).
    await init_db()
    yield
    await close_client()
    await dispose_engine()


app = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
register_kroger_error_handler(app)


@app.exception_handler(LLMError)
async def _handle_llm_error(_request, exc: LLMError):  # noqa: ANN001, ANN202
    # An LLM failure on a synchronous gate (meal extraction, free-text parse) is a
    # truthful upstream error, never an empty success (§9.1).
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=502,
        content={"error": {"code": "llm_error", "message": f"Language model call failed: {exc}"}},
    )


@app.exception_handler(SearchError)
async def _handle_search_error(_request, exc: SearchError):  # noqa: ANN001, ANN202
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=502,
        content={"error": {"code": "search_error", "message": f"Web search failed: {exc}"}},
    )


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(kroger.router)
app.include_router(recipes.router)
app.include_router(plan.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}
