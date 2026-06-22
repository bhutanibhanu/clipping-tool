from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from clipper.media import ffmpeg

_HAS_WHISPER = importlib.util.find_spec("faster_whisper") is not None
_HAS_SAY = shutil.which("say") is not None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _HAS_WHISPER, reason="faster-whisper not installed"),
    pytest.mark.skipif(not ffmpeg.ffmpeg_available(), reason="ffmpeg not available"),
    pytest.mark.skipif(not _HAS_SAY, reason="macOS `say` not available"),
]


def test_transcribe_say_clip(speech_wav: Path) -> None:
    from clipper.transcribe.whisper_local import WhisperTranscriber

    transcript = WhisperTranscriber(model="tiny").transcribe(speech_wav)

    assert len(transcript.segments) >= 1
    for seg in transcript.segments:
        assert seg.start <= seg.end
    # Don't assert exact wording — just that some text came back.
    assert transcript.text.strip() != ""
