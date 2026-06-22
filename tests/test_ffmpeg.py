from __future__ import annotations

import pytest

from clipper.media import ffmpeg


def test_ffmpeg_available_returns_bool() -> None:
    assert isinstance(ffmpeg.ffmpeg_available(), bool)


def test_require_ffmpeg_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    with pytest.raises(ffmpeg.FFmpegNotFoundError):
        ffmpeg.require_ffmpeg()
