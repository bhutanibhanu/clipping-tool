"""Creator catalog: create and look up the authorized creator(s).

v1 manages a single authorized creator, but the data model is multi-row;
these are the thin service functions over ``Creator`` that the CLI and the
later ingest pipeline call. Each takes an explicit ``Session`` so it can be
unit-tested against an in-memory engine.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.db.models import Creator, Source
from clipper.permissions.service import require_permission


class SourceFileNotFoundError(FileNotFoundError):
    """Raised when the video file for a source does not exist on disk."""


def create_creator(
    session: Session,
    name: str,
    *,
    handles: str | None = None,
    notes: str | None = None,
) -> Creator:
    """Create and persist exactly one Creator, returning the populated row."""
    creator = Creator(name=name, handles=handles, notes=notes)
    session.add(creator)
    session.flush()  # assign the primary key without ending the transaction
    return creator


def list_creators(session: Session) -> list[Creator]:
    """Return all creators, oldest first."""
    return list(session.scalars(select(Creator).order_by(Creator.id)))


def get_creator(session: Session, creator_id: int) -> Creator | None:
    """Return the creator with this id, or None if it does not exist."""
    return session.get(Creator, creator_id)


def register_source(session: Session, *, creator_id: int, file_path: Path) -> Source:
    """Register a local video as a Source, gated on the creator's consent.

    Both guards run before anything is persisted: ``file_path`` must exist
    (else ``SourceFileNotFoundError``) and the creator must have an active
    permission (else ``PermissionRequiredError`` via ``require_permission``).
    On success a ``Source`` is created and flushed — linked to the active
    PermissionRecord and storing the file's absolute path — then returned.
    """
    if not file_path.exists():
        raise SourceFileNotFoundError(f"source file not found: {file_path}")

    permission = require_permission(session, creator_id)

    source = Source(
        creator_id=creator_id,
        permission_id=permission.id,
        file_path=str(file_path.resolve()),
    )
    session.add(source)
    session.flush()  # assign the primary key without ending the transaction
    return source
