"""Pure postprocessing for raw detector output.

A `Detector` (Claude, a local OpenAI-compatible model, or the mock) returns
*rough* candidate moments: times that may fall mid-segment, run too short or too
long, sit out of bounds, or near-duplicate one another. These functions clean
that up deterministically — no I/O, no network, no DB — so every provider shares
exactly one notion of "a clean, ranked, non-overlapping clip list".

Pipeline: ``snap → clamp → drop → dedup → rank`` (see `postprocess`).

This module is the canonical home for the clip-length bounds; `mock.py` keeps
its own copy only to stay import-light, but these are the values of record.
"""

from __future__ import annotations

from clipper.detect.base import CandidateClip
from clipper.transcribe.base import Segment

MIN_CLIP_SECONDS = 20.0
MAX_CLIP_SECONDS = 60.0
OVERLAP_THRESHOLD = 0.5


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp `value` into ``[lo, hi]`` (assumes ``lo <= hi``)."""
    return max(lo, min(value, hi))


def snap_to_segments(
    start: float,
    end: float,
    segments: list[Segment],
    source_duration: float,
) -> tuple[float, float]:
    """Snap ``[start, end]`` outward to the enclosing segment boundaries.

    `start` snaps *down* to the start of the segment it falls in; `end` snaps
    *up* to the end of the segment it falls in. Segments are assumed sorted and
    contiguous, so a time sitting exactly on a shared boundary is attributed by
    half-open rules — `start` belongs to the segment it begins (`seg.start <= t
    < seg.end`), `end` to the segment it terminates (`seg.start < t <=
    seg.end`) — which keeps an on-boundary time from being widened spuriously.

    Times outside every segment (or with no segments at all) are simply clamped
    into ``[0, source_duration]``; snapping only applies where a segment encloses
    the time. The returned pair is always clamped to ``[0, source_duration]``.
    """
    snapped_start = start
    for seg in segments:
        if seg.start <= start < seg.end:
            snapped_start = seg.start
            break

    snapped_end = end
    for seg in segments:
        if seg.start < end <= seg.end:
            snapped_end = seg.end
            break

    snapped_start = _clamp(snapped_start, 0.0, source_duration)
    snapped_end = _clamp(snapped_end, 0.0, source_duration)
    return snapped_start, snapped_end


def clamp_duration(
    start: float,
    end: float,
    source_duration: float,
    *,
    min_seconds: float = MIN_CLIP_SECONDS,
    max_seconds: float = MAX_CLIP_SECONDS,
) -> tuple[float, float]:
    """Force ``end - start`` into ``[min_seconds, max_seconds]`` within source bounds.

    Too short → extend, preferring to push `end` later, then `start` earlier,
    staying inside ``[0, source_duration]``. Too long → trim the `end` back to
    ``start + max_seconds``. When the source itself is shorter than
    `min_seconds`, the clip simply spans what exists (``[0, source_duration]``);
    it can't be padded past the media, so the floor is not met — that's expected
    and the caller may still drop it elsewhere.
    """
    start = _clamp(start, 0.0, source_duration)
    end = _clamp(end, 0.0, source_duration)
    duration = end - start

    if duration < min_seconds:
        # Extend the end first (up to the source end)...
        end = min(start + min_seconds, source_duration)
        # ...then, if still short, pull the start earlier (down to 0).
        if end - start < min_seconds:
            start = max(end - min_seconds, 0.0)
    elif duration > max_seconds:
        end = start + max_seconds

    return start, end


def _overlap_ratio(a: CandidateClip, b: CandidateClip) -> float:
    """Intersection of `a` and `b` divided by the *shorter* one's duration.

    Returns ``0.0`` when they don't overlap or either has zero duration. The
    ratio is relative to the shorter clip, so a small clip fully inside a large
    one scores ``1.0`` — i.e. "this clip is mostly already covered".
    """
    intersection = min(a.end, b.end) - max(a.start, b.start)
    if intersection <= 0:
        return 0.0
    shorter = min(a.duration, b.duration)
    if shorter <= 0:
        return 0.0
    return intersection / shorter


def dedup_overlapping(
    candidates: list[CandidateClip],
    *,
    overlap_threshold: float = OVERLAP_THRESHOLD,
) -> list[CandidateClip]:
    """Drop near-duplicate clips that overlap a kept clip by more than the threshold.

    Two clips conflict when their overlap ratio (intersection ÷ shorter
    duration) is strictly greater than `overlap_threshold`. To resolve conflicts
    globally — not just against the first keeper seen — candidates are first
    sorted by preference (higher score, then *longer*, then *earlier*/lower
    `start`), then greedily kept: a candidate is kept only if it conflicts with
    *no* already-kept clip. This guarantees the highest-scored member of any
    overlapping group survives, no two kept clips overlap more than the
    threshold, and the result is independent of input order.

    Because the sweep runs in preference order, the returned list is already
    sorted by descending score (then longer, then earlier); a caller that ranks
    afterwards is therefore doing redundant (but harmless) work.
    """
    # Higher score, then longer, then earlier (lower start) wins — express as an
    # ascending key by negating the "bigger is better" fields.
    ordered = sorted(candidates, key=lambda c: (-c.score, -c.duration, c.start))

    kept: list[CandidateClip] = []
    for cand in ordered:
        if any(_overlap_ratio(cand, keeper) > overlap_threshold for keeper in kept):
            continue  # conflicts with a higher-preference clip already kept — drop it
        kept.append(cand)
    return kept


def postprocess(
    candidates: list[CandidateClip],
    segments: list[Segment],
    source_duration: float,
    *,
    min_seconds: float = MIN_CLIP_SECONDS,
    max_seconds: float = MAX_CLIP_SECONDS,
    overlap_threshold: float = OVERLAP_THRESHOLD,
) -> list[CandidateClip]:
    """Turn raw candidates into a clean, ranked, non-overlapping list.

    Runs ``snap → drop-degenerate → clamp → drop → dedup → rank``:

    1. **snap** each candidate's times out to the enclosing segment boundaries;
    2. **drop** any candidate that is already degenerate after snapping
       (``snapped_end <= snapped_start`` — e.g. raw inverted/zero-length times),
       *before* clamping can fabricate a clip out of it;
    3. **clamp** its duration into ``[min_seconds, max_seconds]`` within source bounds;
    4. **drop** anything still ``end <= start`` (defensive: covers the
       source-shorter-than-min edge);
    5. **dedup** clips overlapping a kept clip by more than `overlap_threshold`,
       keeping the higher-scored (then longer, then earlier);
    6. **rank** the survivors by descending score (ties keep their post-dedup order).

    Every other field (score/reason/title/description/hashtags) is carried
    through unchanged via `model_copy`; only the times are adjusted.
    """
    adjusted: list[CandidateClip] = []
    for cand in candidates:
        start, end = snap_to_segments(cand.start, cand.end, segments, source_duration)
        if end <= start:
            # Raw inverted/zero-length range (e.g. start=90,end=30 or start==end):
            # drop it now so clamp_duration can't extend it into a fabricated clip.
            continue
        start, end = clamp_duration(
            start, end, source_duration, min_seconds=min_seconds, max_seconds=max_seconds
        )
        if end <= start:
            continue  # nothing real left after clamping (source shorter than min) — drop it
        adjusted.append(cand.model_copy(update={"start": start, "end": end}))

    deduped = dedup_overlapping(adjusted, overlap_threshold=overlap_threshold)

    # dedup_overlapping already returns clips in descending-score order; this sort
    # is therefore idempotent, kept only as a defensive guarantee of the contract.
    return sorted(deduped, key=lambda c: c.score, reverse=True)
