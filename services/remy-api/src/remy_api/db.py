"""Async SQLAlchemy engine, session factory, and base metadata.

SQLite via aiosqlite in v1, but the models avoid SQLite-only features (except
FTS5, added later in T3) so switching ``DATABASE_URL`` to Postgres is a config
change, not a rewrite. Foreign-key enforcement is enabled explicitly on SQLite
connections so ``ON DELETE CASCADE`` actually fires.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from remy_api.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _enable_sqlite_fk(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    """Turn on ``PRAGMA foreign_keys`` for SQLite so cascades are honored.

    Also set a ``busy_timeout`` so a background step task (T5 runs discover/match
    as detached asyncio tasks with their own session) and a concurrent request
    session serialize writes instead of failing with "database is locked".
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a file-based SQLite DB if needed."""
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return
    raw_path = database_url[len(prefix) :]
    if not raw_path or raw_path == ":memory:":
        return
    Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _ensure_sqlite_dir(settings.database_url)
        _engine = create_async_engine(settings.database_url, echo=False, future=True)
        if _engine.dialect.name == "sqlite":
            event.listen(_engine.sync_engine, "connect", _enable_sqlite_fk)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory, initializing the engine if necessary."""
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped async session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


def _apply_additive_migrations(conn) -> None:  # noqa: ANN001
    """Add columns introduced after a table already exists in a deployed DB.

    ``create_all`` never alters an existing table, so a column added to a model
    after prod first booted would be missing on the live SQLite file. Applied
    idempotently (guarded by a table-info probe) — no Alembic in v1. Postgres
    users would run a real migration; this is the SQLite-file self-heal path.
    """
    if conn.dialect.name != "sqlite":
        return
    from sqlalchemy import inspect

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())
    # (table, column, DDL type) additive migrations. Note: a *new table* (e.g.
    # ``product_memory``) needs no entry here — ``create_all`` creates missing
    # tables on an existing DB; only new columns on pre-existing tables do.
    additions = [
        ("user_settings", "store_chain", "VARCHAR(64)"),
        ("users", "is_admin", "BOOLEAN NOT NULL DEFAULT 0"),
        ("users", "auth_version", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for table, column, ddl_type in additions:
        if table not in tables:
            continue  # create_all just made it with the column present
        existing = {c["name"] for c in inspector.get_columns(table)}
        if column not in existing:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


async def init_db() -> None:
    """Create all tables. Called from the app lifespan (no Alembic in v1)."""
    # Import models so they register on Base.metadata before create_all.
    from remy_api import models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_additive_migrations)


async def dispose_engine() -> None:
    """Dispose the engine (app shutdown / test teardown)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
