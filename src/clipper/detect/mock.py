"""Deterministic, offline Detector.

Used by tests and for Phase 0 wiring so the pipeline can be exercised end to
end without a network call or an API key. It makes no judgment about clip
quality — it just emits well-formed candidates from the leading segments.
The real bet (judgment quality) is the Claude provider in Phase 2.
"""

from __future__ import annotations

from clipper.detect.base import CandidateClip
from clipper.transcribe.base import Transcript

MIN_CLIP_SECONDS = 20.0
MAX_CLIP_SECONDS = 60.0


class MockDetector:
    """Emits up to `max_clips` deterministic candidates from the transcript."""

    def detect(self, transcript: Transcript, *, max_clips: int = 5) -> list[CandidateClip]:
        out: list[CandidateClip] = []
        for i, seg in enumerate(transcript.segments[:max_clips]):
            start = seg.start
            end = min(max(seg.end, start + MIN_CLIP_SECONDS), start + MAX_CLIP_SECONDS)
            out.append(
                CandidateClip(
                    start=start,
                    end=end,
                    score=round(max(0.0, 1.0 - i * 0.1), 2),
                    reason=f"mock candidate #{i + 1}",
                    title=f"Clip {i + 1}",
                    description=seg.text[:120],
                    hashtags=["#mock"],
                )
            )
        return out
