"""Transcriber contract + transcript value objects.

Transcription is swappable behind this protocol (mirroring the Detector
seam): faster-whisper is the default engine, with whisper.cpp reserved as
the CoreML/Metal escape hatch on the M1 Air. The concrete engine arrives
in Phase 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Segment:
    """A timestamped span of transcript text (segment-level, not word-level)."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    segments: list[Segment]
    language: str | None = None

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments).strip()

    @property
    def duration(self) -> float:
        return self.segments[-1].end if self.segments else 0.0


@runtime_checkable
class Transcriber(Protocol):
    """Produces a timestamped Transcript from a local audio file."""

    def transcribe(self, audio_path: Path) -> Transcript: ...
