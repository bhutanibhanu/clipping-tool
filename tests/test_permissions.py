from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from clipper.catalog import create_creator
from clipper.db.models import PermissionRecord, PermissionStatus
from clipper.db.session import init_db
from clipper.permissions.service import (
    AuthorizationFileNotFoundError,
    active_permission_for,
    grant_permission,
)


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


def _new_creator(session: Session) -> int:
    creator = create_creator(session, name="Authorized Owner")
    session.flush()
    return creator.id


def test_grant_creates_active_record_with_recorded_abs_path(engine: Engine, tmp_path: Path) -> None:
    auth = tmp_path / "consent.pdf"
    auth.write_text("signed authorization")

    with Session(engine) as session:
        creator_id = _new_creator(session)
        record = grant_permission(session, creator_id, "youtube", auth)
        session.commit()

        assert record.status is PermissionStatus.active
        assert record.scope == "youtube"
        # Absolute path recorded; the file itself is not copied/moved.
        assert record.authorization_file_path == str(auth.resolve())
        assert Path(record.authorization_file_path).is_absolute()
        assert auth.exists()


def test_grant_resolves_relative_auth_file_to_absolute(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = tmp_path / "consent.pdf"
    auth.write_text("ok")
    monkeypatch.chdir(tmp_path)

    with Session(engine) as session:
        creator_id = _new_creator(session)
        record = grant_permission(session, creator_id, "youtube", Path("consent.pdf"))
        session.commit()

        assert Path(record.authorization_file_path).is_absolute()
        assert record.authorization_file_path == str(auth.resolve())


def test_grant_with_missing_auth_file_raises_and_persists_nothing(engine: Engine) -> None:
    with Session(engine) as session:
        creator_id = _new_creator(session)
        with pytest.raises(AuthorizationFileNotFoundError):
            grant_permission(session, creator_id, "youtube", Path("/nope/missing.pdf"))
        session.commit()

        assert session.scalar(select(func.count()).select_from(PermissionRecord)) == 0


def test_active_permission_for_returns_active(engine: Engine, tmp_path: Path) -> None:
    auth = tmp_path / "consent.pdf"
    auth.write_text("ok")

    with Session(engine) as session:
        creator_id = _new_creator(session)
        granted = grant_permission(session, creator_id, "youtube", auth)
        session.commit()

        found = active_permission_for(session, creator_id)
        assert found is not None
        assert found.id == granted.id


def test_active_permission_for_skips_revoked(engine: Engine, tmp_path: Path) -> None:
    auth = tmp_path / "consent.pdf"
    auth.write_text("ok")

    with Session(engine) as session:
        creator_id = _new_creator(session)
        record = grant_permission(session, creator_id, "youtube", auth)
        record.status = PermissionStatus.revoked
        session.commit()

        assert active_permission_for(session, creator_id) is None


def test_active_permission_for_none_when_absent(engine: Engine) -> None:
    with Session(engine) as session:
        creator_id = _new_creator(session)
        session.commit()
        assert active_permission_for(session, creator_id) is None


def test_active_permission_for_returns_most_recent_when_multiple(
    engine: Engine, tmp_path: Path
) -> None:
    auth = tmp_path / "consent.pdf"
    auth.write_text("ok")

    with Session(engine) as session:
        creator_id = _new_creator(session)
        grant_permission(session, creator_id, "youtube", auth)
        newer = grant_permission(session, creator_id, "tiktok", auth)
        session.commit()

        found = active_permission_for(session, creator_id)
        assert found is not None
        assert found.id == newer.id
