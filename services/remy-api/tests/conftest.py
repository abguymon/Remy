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
# columns can be inspected as raw bytes).
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="remy-test-")
os.close(_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_DB_PATH}")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from remy_api import models  # noqa: E402,F401  (registers tables on Base.metadata)
from remy_api.db import Base, get_engine  # noqa: E402
from remy_api.main import app  # noqa: E402


@pytest.fixture
def db_path() -> str:
    return _DB_PATH


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Fresh schema per test + an ASGI-transport AsyncClient."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
