"""Detector contract + the structured candidate-clip schema.

This is the heart of the product: a Detector reads a timestamped Transcript
and returns ranked candidate moments with ready-to-edit copy. v1 ships a
Claude provider (Phase 2) behind this protocol; a local LLM can be dropped
in later without touching the pipeline.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from clipper.transcribe.base import Transcript


class DetectorConfigError(RuntimeError):
    """A detector is misconfigured (e.g. a required API key is missing).

    Raised in place of a raw provider/SDK exception so callers get a clear,
    provider-agnostic error at the `Detector` seam — distinct from the
    "model returned nothing usable" case, which returns ``[]`` instead.
    """


class CandidateClip(BaseModel):
    """One detected moment, ready for rendering and operator review."""

    start: float = Field(ge=0, description="Clip start, seconds into the source.")
    end: float = Field(gt=0, description="Clip end, seconds into the source.")
    score: float = Field(ge=0, le=1, description="Model confidence the clip is postable.")
    reason: str = Field(description="Why this moment is clip-worthy.")
    title: str = Field(description="Suggested hook/title.")
    description: str = Field(default="", description="Suggested caption/description.")
    hashtags: list[str] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


@runtime_checkable
class Detector(Protocol):
    """Ranks clip-worthy moments from a transcript."""

    def detect(self, transcript: Transcript, *, max_clips: int = 5) -> list[CandidateClip]: ...
