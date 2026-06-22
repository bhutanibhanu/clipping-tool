"""Tests for permission-gated source registration (T2).

Service-level coverage runs ``register_source`` against an in-memory engine
(never the real ``storage/clipper.db``), seeding a creator + permission exactly
like ``test_permissions.py``. A thin CLI layer is exercised via typer's
``CliRunner`` with storage redirected to ``tmp_path`` like ``test_cli_consent.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from clipper.catalog import SourceFileNotFoundError, create_creator, register_source
from clipper.cli import app
from clipper.config import get_settings
from clipper.db import session as session_mod
from clipper.db.models import PermissionStatus, Source
from clipper.db.session import init_db
from clipper.permissions.service import PermissionRequiredError, grant_permission


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


def _creator_with_active_permission(session: Session, auth: Path) -> tuple[int, int]:
    """Seed a creator + active permission; return (creator_id, permission_id)."""
    creator = create_creator(session, name="Authorized Owner")
    session.flush()
    record = grant_permission(session, creator.id, "youtube", auth)
    return creator.id, record.id


# --- service-level: the gate (the priority coverage) ---------------------------


def test_register_source_with_active_permission_links_correct_permission(
    engine: Engine, tmp_path: Path
) -> None:
    auth = tmp_path / "consent.pdf"
    auth.write_text("signed")
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")

    with Session(engine) as session:
        creator_id, permission_id = _creator_with_active_permission(session, auth)

        source = register_source(session, creator_id=creator_id, file_path=video)
        session.commit()

        assert source.id is not None
        assert source.creator_id == creator_id
        assert source.permission_id == permission_id
        # Absolute path recorded; the file itself is not copied/moved.
        assert source.file_path == str(video.resolve())
        assert Path(source.file_path).is_absolute()
        assert session.scalar(select(func.count()).select_from(Source)) == 1


def test_register_source_without_permission_raises_and_persists_nothing(
    engine: Engine, tmp_path: Path
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")

    with Session(engine) as session:
        creator = create_creator(session, name="Owner")  # no permission granted
        session.flush()

        with pytest.raises(PermissionRequiredError):
            register_source(session, creator_id=creator.id, file_path=video)
        session.commit()

        assert session.scalar(select(func.count()).select_from(Source)) == 0


def test_register_source_with_revoked_permission_raises_and_persists_nothing(
    engine: Engine, tmp_path: Path
) -> None:
    auth = tmp_path / "consent.pdf"
    auth.write_text("signed")
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")

    with Session(engine) as session:
        creator = create_creator(session, name="Owner")
        session.flush()
        record = grant_permission(session, creator.id, "youtube", auth)
        record.status = PermissionStatus.revoked
        session.flush()

        with pytest.raises(PermissionRequiredError):
            register_source(session, creator_id=creator.id, file_path=video)
        session.commit()

        assert session.scalar(select(func.count()).select_from(Source)) == 0


def test_register_source_with_missing_file_raises_and_persists_nothing(
    engine: Engine, tmp_path: Path
) -> None:
    auth = tmp_path / "consent.pdf"
    auth.write_text("signed")

    with Session(engine) as session:
        creator_id, _ = _creator_with_active_permission(session, auth)

        with pytest.raises(SourceFileNotFoundError):
            register_source(
                session, creator_id=creator_id, file_path=tmp_path / "does-not-exist.mp4"
            )
        session.commit()

        assert session.scalar(select(func.count()).select_from(Source)) == 0


# --- CLI-level: happy path + one refusal --------------------------------------

runner = CliRunner()


@pytest.fixture
def storage_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the configured DB at tmp_path and reset the cached settings/engine."""
    monkeypatch.setenv("CLIPPER_STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    session_mod.get_engine.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
    session_mod.get_engine.cache_clear()


def _only_id(pattern: str, text: str) -> int:
    match = re.search(pattern, text)
    assert match is not None, f"could not find id in: {text!r}"
    return int(match.group(1))


def _grant(storage_in_tmp: Path) -> tuple[int, Path]:
    """Create a creator with an active permission via the CLI; return (id, auth path)."""
    add = runner.invoke(app, ["creator", "add", "--name", "Owner"])
    creator_id = _only_id(r"Created creator (\d+)", add.output)
    auth = storage_in_tmp / "consent.pdf"
    auth.write_text("signed")
    grant = runner.invoke(
        app,
        [
            "permission",
            "grant",
            "--creator",
            str(creator_id),
            "--scope",
            "youtube",
            "--auth-file",
            str(auth),
        ],
    )
    assert grant.exit_code == 0, grant.output
    return creator_id, auth


def test_cli_source_add_creates_row_and_prints_id(storage_in_tmp: Path) -> None:
    creator_id, _ = _grant(storage_in_tmp)
    video = storage_in_tmp / "talk.mp4"
    video.write_bytes(b"\x00\x00")

    result = runner.invoke(
        app, ["source", "add", "--file", str(video), "--creator", str(creator_id)]
    )
    assert result.exit_code == 0, result.output
    source_id = _only_id(r"Created source (\d+)", result.output)

    with Session(session_mod.get_engine()) as session:
        source = session.get(Source, source_id)
        assert source is not None
        assert source.creator_id == creator_id
        assert source.file_path == str(video.resolve())


def test_cli_source_add_refused_without_permission_persists_nothing(
    storage_in_tmp: Path,
) -> None:
    add = runner.invoke(app, ["creator", "add", "--name", "Owner"])
    creator_id = _only_id(r"Created creator (\d+)", add.output)
    video = storage_in_tmp / "talk.mp4"
    video.write_bytes(b"\x00\x00")

    result = runner.invoke(
        app, ["source", "add", "--file", str(video), "--creator", str(creator_id)]
    )
    assert result.exit_code != 0

    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 0


def test_cli_source_add_refused_when_file_missing_persists_nothing(
    storage_in_tmp: Path,
) -> None:
    creator_id, _ = _grant(storage_in_tmp)

    result = runner.invoke(
        app,
        ["source", "add", "--file", str(storage_in_tmp / "nope.mp4"), "--creator", str(creator_id)],
    )
    assert result.exit_code != 0

    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Source)) == 0
