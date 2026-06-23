"""Unit tests for the pure detection postprocessors.

Table-driven where it pays off; each test asserts *behavior* (resulting times,
survivors, order) rather than how the functions get there. No I/O, no network,
no model — these are pure functions over plain value objects.
"""

from __future__ import annotations

import pytest

from clipper.detect.base import CandidateClip
from clipper.detect.postprocess import (
    MAX_CLIP_SECONDS,
    MIN_CLIP_SECONDS,
    OVERLAP_THRESHOLD,
    clamp_duration,
    dedup_overlapping,
    postprocess,
    snap_to_segments,
)
from clipper.transcribe.base import Segment

# A simple contiguous transcript used across the snap tests:
#   seg0 [0, 30)  seg1 [30, 65)  seg2 [65, 100]   → source_duration 100.
SEGMENTS = [
    Segment(0.0, 30.0, "alpha"),
    Segment(30.0, 65.0, "bravo"),
    Segment(65.0, 100.0, "charlie"),
]
SOURCE = 100.0


def _clip(start: float, end: float, score: float = 0.5, title: str = "t") -> CandidateClip:
    """Build a candidate, defaulting the non-time fields we don't care about."""
    return CandidateClip(
        start=start,
        end=end,
        score=score,
        reason="because",
        title=title,
        description="desc",
        hashtags=["#tag"],
    )


# --------------------------------------------------------------------------- #
# snap_to_segments                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        # mid-segment on both ends: start down to seg0.start, end up to seg1.end.
        (10.0, 40.0, (0.0, 65.0)),
        # start-of-file: a start of exactly 0 stays at 0 (seg0 encloses it).
        (0.0, 20.0, (0.0, 30.0)),
        # end-of-file: end at the very last boundary snaps up to source end.
        (70.0, 100.0, (65.0, 100.0)),
        # spans all three segments.
        (5.0, 95.0, (0.0, 100.0)),
        # exact interior boundary: start==30 belongs to seg1 (half-open start),
        # end==30 belongs to seg0 (half-open end) → already on boundaries, no widen.
        (30.0, 30.0, (30.0, 30.0)),
        # exact boundary as the *end*: end==65 is seg1's end, start==65 is seg2's
        # start — neither needs widening.
        (65.0, 65.0, (65.0, 65.0)),
    ],
)
def test_snap_to_segments(start: float, end: float, expected: tuple[float, float]) -> None:
    assert snap_to_segments(start, end, SEGMENTS, SOURCE) == expected


def test_snap_clamps_times_outside_all_segments() -> None:
    # A negative start and a past-the-end end have no enclosing segment, so they
    # are not snapped — only clamped into [0, source_duration].
    assert snap_to_segments(-5.0, 150.0, SEGMENTS, SOURCE) == (0.0, 100.0)


def test_snap_with_no_segments_just_clamps() -> None:
    assert snap_to_segments(10.0, 40.0, [], SOURCE) == (10.0, 40.0)
    assert snap_to_segments(-1.0, 200.0, [], SOURCE) == (0.0, 100.0)


# --------------------------------------------------------------------------- #
# clamp_duration                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("start", "end", "source", "expected"),
    [
        # Already in range — untouched.
        (10.0, 40.0, 100.0, (10.0, 40.0)),
        # Too short, room to extend the END (preferred): 5..10 → 5..25.
        (5.0, 10.0, 100.0, (5.0, 25.0)),
        # Too short AND near the end: extend end to source, then pull start back.
        # 90..95 (src 100): end can only reach 100, so start drops to 80 → 20s.
        (90.0, 95.0, 100.0, (80.0, 100.0)),
        # Too long — trim the end back to start + MAX.
        (0.0, 80.0, 100.0, (0.0, 60.0)),
        # Exactly MIN and exactly MAX are both in range (inclusive bounds).
        (0.0, MIN_CLIP_SECONDS, 100.0, (0.0, MIN_CLIP_SECONDS)),
        (0.0, MAX_CLIP_SECONDS, 100.0, (0.0, MAX_CLIP_SECONDS)),
    ],
)
def test_clamp_duration(
    start: float, end: float, source: float, expected: tuple[float, float]
) -> None:
    assert clamp_duration(start, end, source) == expected


def test_clamp_duration_source_shorter_than_min() -> None:
    # The media is only 12s — shorter than MIN. We can't pad past it, so the clip
    # spans the whole source and stays sub-MIN (the caller may drop it later).
    start, end = clamp_duration(0.0, 12.0, 12.0)
    assert (start, end) == (0.0, 12.0)
    assert end - start < MIN_CLIP_SECONDS


# --------------------------------------------------------------------------- #
# dedup_overlapping                                                           #
# --------------------------------------------------------------------------- #


def test_dedup_full_overlap_keeps_higher_score() -> None:
    high = _clip(0.0, 30.0, score=0.9, title="high")
    low = _clip(0.0, 30.0, score=0.4, title="low")
    # Order shouldn't matter: the higher score survives either way.
    assert [c.title for c in dedup_overlapping([low, high])] == ["high"]
    assert [c.title for c in dedup_overlapping([high, low])] == ["high"]


def test_dedup_partial_overlap_above_threshold_drops_one() -> None:
    # a = [0,40] (40s), b = [30,50] (20s). intersection = 10 over shorter(20)
    # = 0.5 — NOT > 0.5, so this pair would survive. Tighten b to force > 0.5:
    # b = [25,45] (20s): intersection [25,40] = 15 / 20 = 0.75 > 0.5 → drop lower.
    a = _clip(0.0, 40.0, score=0.8, title="a")
    b = _clip(25.0, 45.0, score=0.6, title="b")
    assert [c.title for c in dedup_overlapping([a, b])] == ["a"]


def test_dedup_partial_overlap_below_threshold_keeps_both() -> None:
    # a = [0,40] (40s), b = [30,50] (20s): intersection [30,40] = 10 / 20 = 0.5,
    # which is NOT strictly greater than 0.5 → both must survive.
    a = _clip(0.0, 40.0, score=0.8, title="a")
    b = _clip(30.0, 50.0, score=0.6, title="b")
    kept = dedup_overlapping([a, b])
    assert {c.title for c in kept} == {"a", "b"}


def test_dedup_no_overlap_keeps_both() -> None:
    a = _clip(0.0, 30.0, score=0.5, title="a")
    b = _clip(60.0, 90.0, score=0.5, title="b")
    assert len(dedup_overlapping([a, b])) == 2


def test_dedup_equal_score_keeps_longer() -> None:
    # Same score, fully overlapping: the longer clip wins, regardless of order.
    longer = _clip(0.0, 40.0, score=0.7, title="longer")
    shorter = _clip(0.0, 25.0, score=0.7, title="shorter")
    assert [c.title for c in dedup_overlapping([shorter, longer])] == ["longer"]
    assert [c.title for c in dedup_overlapping([longer, shorter])] == ["longer"]


def test_dedup_equal_score_equal_length_keeps_earlier() -> None:
    # Same score, same length, overlapping > 50%: the earlier (lower start) wins.
    early = _clip(0.0, 30.0, score=0.7, title="early")
    late = _clip(5.0, 35.0, score=0.7, title="late")  # 25s overlap / 30 = 0.83
    assert [c.title for c in dedup_overlapping([late, early])] == ["early"]
    assert [c.title for c in dedup_overlapping([early, late])] == ["early"]


def test_dedup_three_way_overlap_keeps_highest_not_just_first_conflict() -> None:
    # A 3-way case the OLD greedy (first-conflict) dedup got wrong: a mid-scored
    # candidate overlaps two others. Globally it must lose to the highest-scored
    # clip it conflicts with and be dropped — not survive by displacing a lower
    # keeper while still >50%-overlapping a higher one.
    #   top    = [0,40]  (40s) score 0.9
    #   mid    = [10,40] (30s) score 0.6 — overlap w/ top = 30/30 = 1.0 (> 0.5)
    #   low    = [12,40] (28s) score 0.3 — overlap w/ top = 28/28 = 1.0 (> 0.5)
    top = _clip(0.0, 40.0, score=0.9, title="top")
    mid = _clip(10.0, 40.0, score=0.6, title="mid")
    low = _clip(12.0, 40.0, score=0.3, title="low")
    # Feed in an order that would have tripped the old order-sensitive logic.
    for order in ([mid, low, top], [top, mid, low], [low, mid, top]):
        kept = dedup_overlapping(order)
        assert [c.title for c in kept] == ["top"], order

    # Now a mix where a separate group survives intact alongside the winner.
    #   other  = [100,140] (40s) score 0.5 — disjoint from the [0,40] cluster.
    other = _clip(100.0, 140.0, score=0.5, title="other")
    kept = dedup_overlapping([mid, other, low, top])
    titles = {c.title for c in kept}
    assert titles == {"top", "other"}
    # The highest-scored of the overlapping group survived...
    assert "top" in titles and "mid" not in titles and "low" not in titles
    # ...and no two survivors overlap by more than the threshold.
    for i in range(len(kept)):
        for j in range(i + 1, len(kept)):
            inter = min(kept[i].end, kept[j].end) - max(kept[i].start, kept[j].start)
            shorter = min(kept[i].duration, kept[j].duration)
            ratio = inter / shorter if inter > 0 and shorter > 0 else 0.0
            assert ratio <= OVERLAP_THRESHOLD


def test_dedup_output_is_score_sorted() -> None:
    # The greedy sweep runs in preference order, so the result is already ranked.
    a = _clip(0.0, 30.0, score=0.3, title="a")
    b = _clip(100.0, 130.0, score=0.9, title="b")
    c = _clip(200.0, 230.0, score=0.6, title="c")
    assert [x.score for x in dedup_overlapping([a, b, c])] == [0.9, 0.6, 0.3]


# --------------------------------------------------------------------------- #
# postprocess (the full pipeline)                                             #
# --------------------------------------------------------------------------- #


def test_postprocess_drops_zero_length_after_snap() -> None:
    # start==end==30 sits exactly on the seg0/seg1 boundary, so it is not
    # widened by snapping; clamping can't extend a point that has room only if
    # there were duration — here end<=start, so it's dropped entirely.
    #
    # To make the drop unambiguous, use a degenerate clip whose snapped, clamped
    # form still collapses: source_duration 0 → everything clamps to [0,0].
    cand = _clip(10.0, 40.0)
    assert postprocess([cand], SEGMENTS, 0.0) == []


def test_postprocess_drops_raw_zero_length_not_extends() -> None:
    # Raw start==end==30 (a zero-length point). It snaps to (30,30) and must be
    # DROPPED before clamp_duration can fabricate a 20s clip from it — the bug.
    assert postprocess([_clip(30.0, 30.0)], SEGMENTS, SOURCE) == []


def test_postprocess_drops_raw_inverted_range_not_extends() -> None:
    # Raw start=90, end=30 (inverted). Snapping yields (65, 30) — still inverted —
    # so it is dropped, not extended by clamp into a fabricated [65, 85] clip.
    assert postprocess([_clip(90.0, 30.0)], SEGMENTS, SOURCE) == []


def test_postprocess_drops_candidate_degenerate_after_snap() -> None:
    # Raw times are ordered (50 < 70) but both lie past a short 40 s source, so
    # snap_to_segments clamps them to (40, 40) — degenerate after snapping. It
    # must be dropped rather than clamped up into a fabricated clip.
    short_segs = [Segment(0.0, 40.0, "only")]
    assert postprocess([_clip(50.0, 70.0)], short_segs, 40.0) == []


def test_postprocess_drops_mid_segment_zero_length_not_widened() -> None:
    # Codex round-2 regression: with one wide segment, a raw zero-length point
    # (50, 50) would snap OUTWARD to (0, 100). The raw end<=start drop must catch
    # it BEFORE snapping, or it gets fabricated into a clip.
    one_seg = [Segment(0.0, 100.0, "one wide segment")]
    assert postprocess([_clip(50.0, 50.0)], one_seg, 100.0) == []


def test_postprocess_drops_mid_segment_reversed_not_widened() -> None:
    # Same hole for a reversed raw range (60, 50) — would also snap to (0, 100).
    one_seg = [Segment(0.0, 100.0, "one wide segment")]
    assert postprocess([_clip(60.0, 50.0)], one_seg, 100.0) == []


def test_postprocess_snaps_then_clamps_too_long() -> None:
    # [10,40] snaps to [0,65] (65s), then clamps (too long) to [0,60].
    [out] = postprocess([_clip(10.0, 40.0)], SEGMENTS, SOURCE)
    assert (out.start, out.end) == (0.0, 60.0)


def test_postprocess_snaps_then_extends_too_short() -> None:
    # A tiny clip inside seg0: [2,5] snaps to [0,30] (30s) — already in range,
    # no extension needed. Use a clip that snaps short instead: there is no
    # sub-20s segment here, so assert the in-range snap result directly.
    [out] = postprocess([_clip(2.0, 5.0)], SEGMENTS, SOURCE)
    assert (out.start, out.end) == (0.0, 30.0)
    assert MIN_CLIP_SECONDS <= out.duration <= MAX_CLIP_SECONDS


def test_postprocess_short_segment_gets_extended() -> None:
    # A transcript whose segments are short forces the extend path through the
    # full pipeline: seg [0,8) then a long tail. [1,3] snaps to [0,8] (8s, too
    # short) and extends the end to 20s.
    segs = [Segment(0.0, 8.0, "x"), Segment(8.0, 200.0, "y")]
    [out] = postprocess([_clip(1.0, 3.0)], segs, 200.0)
    assert out.start == 0.0
    assert out.duration == pytest.approx(MIN_CLIP_SECONDS)


def test_postprocess_ranks_survivors_by_descending_score() -> None:
    # Three non-overlapping clips given out of order come back sorted by score.
    cands = [
        _clip(0.0, 30.0, score=0.3, title="c"),
        _clip(120.0, 150.0, score=0.9, title="a"),
        _clip(60.0, 90.0, score=0.6, title="b"),
    ]
    segs = [
        Segment(0.0, 30.0, "0"),
        Segment(60.0, 90.0, "1"),
        Segment(120.0, 150.0, "2"),
    ]
    out = postprocess(cands, segs, 200.0)
    assert [c.title for c in out] == ["a", "b", "c"]
    assert [c.score for c in out] == [0.9, 0.6, 0.3]


def test_postprocess_dedups_overlap_then_ranks() -> None:
    # Two heavily-overlapping clips (keep higher score) plus a distinct third.
    overlap_hi = _clip(0.0, 30.0, score=0.5, title="hi")
    overlap_lo = _clip(0.0, 28.0, score=0.4, title="lo")  # ~0.93 overlap of shorter
    distinct = _clip(60.0, 90.0, score=0.8, title="distinct")
    segs = [
        Segment(0.0, 30.0, "0"),
        Segment(60.0, 90.0, "1"),
    ]
    out = postprocess([overlap_hi, overlap_lo, distinct], segs, 100.0)
    assert [c.title for c in out] == ["distinct", "hi"]


def test_postprocess_preserves_non_time_fields() -> None:
    cand = CandidateClip(
        start=10.0,
        end=40.0,
        score=0.77,
        reason="great hook",
        title="My Title",
        description="My description",
        hashtags=["#one", "#two"],
    )
    [out] = postprocess([cand], SEGMENTS, SOURCE)
    # Times were adjusted...
    assert (out.start, out.end) == (0.0, 60.0)
    # ...but everything else carried through untouched.
    assert out.score == 0.77
    assert out.reason == "great hook"
    assert out.title == "My Title"
    assert out.description == "My description"
    assert out.hashtags == ["#one", "#two"]


def test_postprocess_empty_input_returns_empty() -> None:
    assert postprocess([], SEGMENTS, SOURCE) == []
