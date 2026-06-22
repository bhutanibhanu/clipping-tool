from __future__ import annotations

from pathlib import Path

import pytest

from clipper.media import ffmpeg
from clipper.transcribe.base import Segment, Transcript


@pytest.fixture
def transcript() -> Transcript:
    return Transcript(
        segments=[
            Segment(0.0, 6.0, "Welcome to the show, today we have a great guest."),
            Segment(6.0, 30.0, "Here is a genuinely interesting story about the early days."),
            Segment(30.0, 75.0, "And then came the surprising twist that changed everything."),
        ],
        language="en",
    )


@pytest.fixture
def synthetic_clip(tmp_path: Path) -> Path:
    """A ~10 s 320x240 lavfi test clip (video + 440 Hz tone) under tmp_path.

    Requires ffmpeg; integration tests using this fixture skip when it is
    unavailable. Generated via the safe arg-list wrapper (no shell string).
    """
    if not ffmpeg.ffmpeg_available():
        pytest.skip("ffmpeg not available")
    out = tmp_path / "clip.mp4"
    ffmpeg.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=10:size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=10",
            "-shortest",
            str(out),
        ]
    )
    return out
