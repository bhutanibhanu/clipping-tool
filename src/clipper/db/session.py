"""Engine + schema creation helpers."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine

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
