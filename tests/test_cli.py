from __future__ import annotations

from typer.testing import CliRunner

from clipper import __version__
from clipper.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_doctor_runs() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "clipper" in result.stdout
    assert "whisper model" in result.stdout
