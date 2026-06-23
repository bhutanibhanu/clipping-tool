"""Detection orchestration: run a `Detector` over a source and persist clips.

This is the glue between the `Detector` providers (Claude, OpenAI-compatible,
mock) and the database. It loads a source's stored `Transcript`, asks the
injected detector for ranked candidates, derives each candidate's
``transcript_excerpt`` *locally* (slicing the transcript, never trusting the
model to echo it back faithfully — ADR-0001), and maps the survivors into
pending `Clip` rows field-for-field.

The detector is injected so unit tests use `MockDetector` with no network or
key. ``persist=False`` (the eval path T5 will use) runs the same detection but
returns the raw `CandidateClip`s without writing any rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.orm import Session

from clipper.config import get_settings
from clipper.db.models import Clip, ClipStatus, Source
from clipper.detect.base import CandidateClip, Detector
from clipper.transcribe.base import Segment
from clipper.transcribe.store import load_transcript

# The provider names the CLI exposes; kept here so the selector is the single
# source of truth (the CLI just surfaces these as a typer choice).
PROVIDER_CLAUDE = "claude"
PROVIDER_OPENAI_COMPAT = "openai-compat"
PROVIDER_MOCK = "mock"
PROVIDER_NAMES = (PROVIDER_CLAUDE, PROVIDER_OPENAI_COMPAT, PROVIDER_MOCK)


class SourceNotFoundError(LookupError):
    """Raised when ``detect_for_source`` is given a source id that does not exist."""


class TranscriptMissingError(RuntimeError):
    """Raised when a source has no transcript to detect against (ingest not run)."""


class UnknownProviderError(ValueError):
    """Raised when an unrecognized detection provider name is requested."""


def make_detector(provider: str) -> Detector:
    """Map a provider name to a `Detector` instance.

    ``"claude"`` → `ClaudeDetector`, ``"openai-compat"`` → `OpenAICompatDetector`,
    ``"mock"`` → `MockDetector`. Any other name raises `UnknownProviderError`.
    Imports are local so selecting the mock never imports the `anthropic`/`httpx`
    provider modules (and constructing a provider never opens a connection).
    """
    if provider == PROVIDER_MOCK:
        from clipper.detect.mock import MockDetector

        return MockDetector()
    if provider == PROVIDER_CLAUDE:
        from clipper.detect.claude import ClaudeDetector

        return ClaudeDetector()
    if provider == PROVIDER_OPENAI_COMPAT:
        from clipper.detect.openai_compat import OpenAICompatDetector

        return OpenAICompatDetector()
    raise UnknownProviderError(
        f"unknown detection provider {provider!r}; expected one of {', '.join(PROVIDER_NAMES)}"
    )


def excerpt_for(segments: Sequence[Segment], start: float, end: float) -> str:
    """Concatenate the text of transcript segments overlapping ``[start, end]``.

    A segment overlaps the clip window when it starts before the window ends and
    ends after the window starts (``seg.start < end and seg.end > start``) — so a
    segment merely touching a boundary (``seg.end == start``) is excluded. The
    surviving segment texts are stripped and joined with a single space. This is
    the *locally derived* excerpt persisted on the `Clip`; it is never taken from
    the model.
    """
    texts = [
        seg.text.strip()
        for seg in segments
        if seg.start < end and seg.end > start and seg.text.strip()
    ]
    return " ".join(texts)


def detect_candidates_for_source(
    session: Session,
    source_id: int,
    *,
    detector: Detector,
    max_clips: int | None = None,
) -> tuple[list[CandidateClip], list[Segment]]:
    """Load ``source_id``'s transcript and return ranked candidates + its segments.

    The shared core of both the persist path (`detect_for_source`) and the eval
    path (`clipper detect --eval`): it resolves the `Source`
    (``SourceNotFoundError`` if absent), refuses with ``TranscriptMissingError``
    when there is no ``transcript_path`` (ingest hasn't run), loads the
    `Transcript`, and calls ``detector.detect(transcript, max_clips=...)``
    (providers already postprocess/rank). It returns the raw `CandidateClip`s
    **and** the transcript's segments so callers can derive excerpts (via
    `excerpt_for`) without loading the transcript a second time. Persists
    nothing.
    """
    if max_clips is None:
        max_clips = get_settings().detector_max_clips

    source = session.get(Source, source_id)
    if source is None:
        raise SourceNotFoundError(f"source {source_id} not found")
    if not source.transcript_path:
        raise TranscriptMissingError(
            f"source {source_id} has no transcript; run `clipper ingest {source_id}` first"
        )

    transcript = load_transcript(Path(source.transcript_path))
    candidates = detector.detect(transcript, max_clips=max_clips)
    return candidates, transcript.segments


def detect_for_source(
    session: Session,
    source_id: int,
    *,
    detector: Detector,
    max_clips: int | None = None,
    persist: bool = True,
) -> list[Clip] | list[CandidateClip]:
    """Run `detector` over ``source_id``'s transcript and (optionally) persist clips.

    Looks up the `Source` (``SourceNotFoundError`` if absent) and refuses with
    ``TranscriptMissingError`` — persisting nothing — when it has no
    ``transcript_path`` (ingest hasn't produced one). Otherwise it loads the
    `Transcript`, calls ``detector.detect(transcript, max_clips=...)`` (providers
    already postprocess/rank), and derives each candidate's
    ``transcript_excerpt`` locally via `excerpt_for`.

    When ``persist`` is true (the CLI path) it creates one pending `Clip` row per
    candidate — mapping ``start→start_seconds``, ``end→end_seconds`` and copying
    ``score``/``reason``/``title``/``description``/``hashtags`` — adds and flushes
    them, and returns the `Clip` rows. Persisted times are clamped into
    ``[0, source.duration_seconds]`` (the acceptance invariant) when the source
    duration is known; a candidate that collapses to ``end <= start`` after
    clamping (i.e. lies fully out of bounds) is skipped, and the
    ``transcript_excerpt`` is derived from the *clamped* window. When the source
    duration is unknown (``None``) times are persisted as-is. When ``persist`` is
    false (the eval path) it returns the `CandidateClip`s unchanged and writes
    nothing.
    """
    candidates, segments = detect_candidates_for_source(
        session, source_id, detector=detector, max_clips=max_clips
    )

    if not persist:
        return candidates

    # Already loaded by detect_candidates_for_source — served from the identity map.
    source = session.get(Source, source_id)
    duration = source.duration_seconds if source is not None else None

    clips: list[Clip] = []
    for cand in candidates:
        start, end = cand.start, cand.end
        if duration is not None:
            start = max(0.0, min(start, duration))
            end = max(0.0, min(end, duration))
            if end <= start:
                continue  # fully out of bounds / degenerate after clamping — skip it
        clip = Clip(
            source_id=source_id,
            start_seconds=start,
            end_seconds=end,
            status=ClipStatus.pending,
            score=cand.score,
            reason=cand.reason,
            title=cand.title,
            description=cand.description,
            hashtags=list(cand.hashtags),
            transcript_excerpt=excerpt_for(segments, start, end),
        )
        session.add(clip)
        clips.append(clip)
    session.flush()  # assign primary keys without ending the transaction
    return clips
