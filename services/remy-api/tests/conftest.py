"""Test fixtures.

The app validates config fail-closed at import time and reads ``DATABASE_URL``
when the engine is first built, so valid secrets and a throwaway SQLite file
must be set in the environment before ``remy_api`` modules are imported. These
are throwaway test values, never real credentials.
"""

import os
import tempfile

from cryptography.fernet import Fernet

os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production-use-only")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

# Isolated on-disk SQLite DB for the whole test session (a real file so encrypted
# columns can be inspected as raw bytes). These are FORCE-assigned, never
# ``setdefault``: the test session drops/recreates all tables, so inheriting an
# ambient ``DATABASE_URL`` (e.g. a sourced deployment env pointing at the live
# dev DB) would silently wipe real data. Tests must always use a throwaway file.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="remy-test-")
os.close(_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"

# Recipe images go to a throwaway temp dir so tests never touch the repo data dir.
_IMAGES_DIR = tempfile.mkdtemp(prefix="remy-test-images-")
os.environ["RECIPE_IMAGES_DIR"] = _IMAGES_DIR

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from remy_api import models  # noqa: E402,F401  (registers tables on Base.metadata)
from remy_api.db import Base, get_engine, get_session_factory  # noqa: E402
from remy_api.main import app  # noqa: E402


@pytest.fixture
def db_path() -> str:
    return _DB_PATH


@pytest.fixture
def images_dir() -> str:
    return _IMAGES_DIR


async def _reset_schema() -> None:
    from sqlalchemy import text

    from remy_api.recipes import store as _store

    engine = get_engine()
    async with engine.begin() as conn:
        # recipe_fts is a raw FTS5 virtual table (not in Base.metadata), so it must
        # be dropped explicitly or stale rows leak across tests and skew search.
        await conn.execute(text("DROP TABLE IF EXISTS recipe_fts"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    _store._fts_available = None


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Fresh schema per test + an ASGI-transport AsyncClient."""
    await _reset_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def session():
    """Fresh schema per test + a raw async session (no HTTP layer)."""
    await _reset_schema()
    factory = get_session_factory()
    async with factory() as s:
        yield s
