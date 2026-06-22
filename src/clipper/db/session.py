"""Engine + schema creation helpers and the per-operation session context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from clipper.config import get_settings
from clipper.db.models import Base


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    """Turn on SQLite FK enforcement for every connection on every engine.

    SQLite ignores ``FOREIGN KEY`` constraints unless ``PRAGMA foreign_keys``
    is set per-connection. Listening on the base ``Engine`` class applies this
    to all app engines (including in-memory test engines), so orphan
    ``creator_id`` / ``permission_id`` rows are rejected at the DB layer. The
    pragma is a no-op on non-SQLite connections, but we guard on the dialect's
    cursor type defensively and only issue it when the driver looks like
    SQLite's.
    """
    # Only SQLite DBAPI connections expose this pragma; skip others safely.
    if dbapi_connection.__class__.__module__.split(".")[0] not in ("sqlite3", "pysqlite2"):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def make_engine(db_url: str | None = None) -> Engine:
    url = db_url or get_settings().db_url
    return create_engine(url, echo=False)


def init_db(engine: Engine | None = None) -> Engine:
    """Create the storage dir (for file-backed SQLite) and all tables."""
    eng = engine or make_engine()
    settings = get_settings()
    if eng.url.database not in (None, ":memory:"):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(eng)
    return eng


@lru_cache
def get_engine() -> Engine:
    """Return the cached engine for the configured (file-backed) DB.

    The DB and its tables are created on first use, so the storage dir need
    not exist beforehand — the first write initializes it.
    """
    return init_db(make_engine())


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Yield a Session, committing on success and rolling back on error.

    With no engine, this targets the configured DB (created if absent), so
    CLI commands can simply ``with session_scope() as session:``. Service
    functions instead take a ``Session`` argument so they stay unit-testable
    against an in-memory engine.
    """
    eng = engine or get_engine()
    session = Session(eng)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
