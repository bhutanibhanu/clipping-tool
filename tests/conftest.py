from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from clipper.media import ffmpeg
from clipper.media.audio import extract_audio
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


@pytest.fixture
def speech_wav(tmp_path: Path) -> Path:
    """A 16 kHz mono WAV of synthesized speech (via macOS `say` + ffmpeg).

    Integration transcription tests use this; they skip when `say`/ffmpeg are
    unavailable (e.g. CI/Linux), so the synthesis is guarded here too.
    """
    if shutil.which("say") is None:
        pytest.skip("macOS `say` not available")
    if not ffmpeg.ffmpeg_available():
        pytest.skip("ffmpeg not available")

    aiff = tmp_path / "speech.aiff"
    subprocess.run(
        ["say", "-o", str(aiff), "The quick brown fox jumps over the lazy dog."],
        check=True,
        capture_output=True,
    )
    return extract_audio(aiff, tmp_path / "speech.wav")
