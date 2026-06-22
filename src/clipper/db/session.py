"""Engine + schema creation helpers and the per-operation session context."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from clipper.config import get_settings
from clipper.db.models import Base


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
