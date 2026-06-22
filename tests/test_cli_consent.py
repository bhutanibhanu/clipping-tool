"""CLI-level tests for `creator add` and `permission grant`.

These exercise the real session path, so they redirect storage to a
``tmp_path`` DB (never the real ``storage/clipper.db``) by setting
``CLIPPER_STORAGE_DIR`` and clearing the cached settings + engine.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from clipper.cli import app
from clipper.config import get_settings
from clipper.db import session as session_mod
from clipper.db.models import Creator, PermissionRecord, PermissionStatus

runner = CliRunner()


@pytest.fixture(autouse=True)
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


def test_creator_add_creates_one_row_and_prints_id(storage_in_tmp: Path) -> None:
    result = runner.invoke(app, ["creator", "add", "--name", "Owner"])
    assert result.exit_code == 0, result.output
    creator_id = _only_id(r"Created creator (\d+)", result.output)

    # DB created under the redirected storage dir, not the real one.
    assert (storage_in_tmp / "storage" / "clipper.db").exists()
    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Creator)) == 1
        assert session.get(Creator, creator_id) is not None


def test_permission_grant_persists_active_record(storage_in_tmp: Path) -> None:
    add = runner.invoke(app, ["creator", "add", "--name", "Owner"])
    creator_id = _only_id(r"Created creator (\d+)", add.output)

    auth = storage_in_tmp / "consent.pdf"
    auth.write_text("signed")

    result = runner.invoke(
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
    assert result.exit_code == 0, result.output

    with Session(session_mod.get_engine()) as session:
        record = session.scalars(select(PermissionRecord)).one()
        assert record.creator_id == creator_id
        assert record.status is PermissionStatus.active
        assert record.authorization_file_path == str(auth.resolve())


def test_permission_grant_missing_file_exits_nonzero_and_persists_nothing(
    storage_in_tmp: Path,
) -> None:
    add = runner.invoke(app, ["creator", "add", "--name", "Owner"])
    creator_id = _only_id(r"Created creator (\d+)", add.output)

    result = runner.invoke(
        app,
        [
            "permission",
            "grant",
            "--creator",
            str(creator_id),
            "--scope",
            "youtube",
            "--auth-file",
            str(storage_in_tmp / "does-not-exist.pdf"),
        ],
    )
    assert result.exit_code != 0

    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(PermissionRecord)) == 0


def test_permission_grant_unknown_creator_exits_nonzero_and_persists_nothing(
    storage_in_tmp: Path,
) -> None:
    # The DB exists but has no Creator with id 999; the auth file is valid so the
    # only failing guard is the creator-existence check.
    runner.invoke(app, ["creator", "add", "--name", "Owner"])  # creates the DB + creator 1
    auth = storage_in_tmp / "consent.pdf"
    auth.write_text("signed")

    result = runner.invoke(
        app,
        [
            "permission",
            "grant",
            "--creator",
            "999",
            "--scope",
            "youtube",
            "--auth-file",
            str(auth),
        ],
    )
    assert result.exit_code != 0
    assert "999" in result.output  # the clear error names the missing creator

    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(PermissionRecord)) == 0


def test_existing_commands_intact() -> None:
    assert runner.invoke(app, ["version"]).exit_code == 0
    assert runner.invoke(app, ["doctor"]).exit_code == 0
