"""Remy v2 API entrypoint.

Validates configuration fail-closed at import time (so a misconfigured
deployment fails immediately rather than serving broken endpoints) and exposes
a ``/health`` endpoint.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from remy_api import __version__
from remy_api.config import get_settings

# Fail closed: importing the app validates required secrets. A misconfigured
# container exits here with a clear ConfigError rather than starting.
settings = get_settings()

app = FastAPI(title=settings.api_title, version=settings.api_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": __version__}
