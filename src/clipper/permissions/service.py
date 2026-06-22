"""Permission records: grant consent and look up the active record.

A ``PermissionRecord`` is the proof-of-consent gate the pipeline enforces
before any source is processed. Granting one records the absolute path of an
authorization file the operator already has on disk (the file is *not*
copied — provenance/export handles that later). Lookups never return a
revoked record. Both functions take an explicit ``Session`` for testability.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from clipper.db.models import Creator, PermissionRecord, PermissionStatus


class AuthorizationFileNotFoundError(FileNotFoundError):
    """Raised when the authorization file for a grant does not exist on disk."""


class CreatorNotFoundError(LookupError):
    """Raised when a grant references a creator id that has no ``Creator`` row.

    Granting a permission to a nonexistent creator would create an orphan
    consent record the gate would then trust, so the existence check happens
    *before* anything is persisted.
    """


class PermissionRequiredError(Exception):
    """Raised when an operation needs an active permission the creator lacks.

    This is the account-safety gate: a Source must never be processed (or even
    registered) without proof of consent on file for its creator.
    """


def grant_permission(
    session: Session,
    creator_id: int,
    scope: str,
    auth_file: Path,
) -> PermissionRecord:
    """Persist an active PermissionRecord for ``creator_id``.

    Both guards run before anything is persisted: ``creator_id`` must reference
    an existing ``Creator`` (else ``CreatorNotFoundError``) and ``auth_file``
    must exist (else ``AuthorizationFileNotFoundError``). On success the
    file's absolute path is recorded (the file itself is left in place, not
    copied). A failed check persists nothing.
    """
    if session.get(Creator, creator_id) is None:
        raise CreatorNotFoundError(
            f"creator {creator_id} not found; create the creator before granting permission"
        )
    if not auth_file.exists():
        raise AuthorizationFileNotFoundError(f"authorization file not found: {auth_file}")

    record = PermissionRecord(
        creator_id=creator_id,
        scope=scope,
        authorization_file_path=str(auth_file.resolve()),
        status=PermissionStatus.active,
    )
    session.add(record)
    session.flush()  # assign the primary key without ending the transaction
    return record


def active_permission_for(session: Session, creator_id: int) -> PermissionRecord | None:
    """Return the most recent active PermissionRecord for the creator, else None.

    A ``revoked`` record is never returned.
    """
    stmt = (
        select(PermissionRecord)
        .where(
            PermissionRecord.creator_id == creator_id,
            PermissionRecord.status == PermissionStatus.active,
        )
        .order_by(PermissionRecord.granted_at.desc(), PermissionRecord.id.desc())
    )
    return session.scalars(stmt).first()


def require_permission(session: Session, creator_id: int) -> PermissionRecord:
    """Return the creator's active PermissionRecord or raise ``PermissionRequiredError``.

    The enforcement gate: defers the active/revoked logic to
    ``active_permission_for`` and only converts a ``None`` result into a hard
    failure, so callers can register/process a Source solely when consent is on
    file.
    """
    record = active_permission_for(session, creator_id)
    if record is None:
        raise PermissionRequiredError(
            f"creator {creator_id} has no active permission record; grant one first"
        )
    return record
