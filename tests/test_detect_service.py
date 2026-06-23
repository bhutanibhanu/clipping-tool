"""Tests for detection persistence + the `clipper detect` command (T4).

Service-level coverage runs ``detect_for_source`` against an in-memory engine
(never the real ``storage/clipper.db``) with the offline `MockDetector`, so no
network or API key is touched. It seeds a creator + active permission + a
registered Source exactly like ``test_pipeline_ingest.py``, writes a real
transcript JSON via ``save_transcript`` (the path detection loads from), and
asserts: pending clips are persisted with populated, in-bounds fields and a
non-empty *locally derived* excerpt; a source with no transcript is refused with
nothing persisted; ``persist=False`` returns candidates and writes no rows; and
the provider selector resolves each name to the right class. ``excerpt_for`` gets
a direct unit test. A thin CLI layer is exercised via typer's ``CliRunner`` with
storage redirected to ``tmp_path`` like ``test_sources.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from clipper.catalog import create_creator, register_source
from clipper.cli import app
from clipper.config import get_settings
from clipper.db import session as session_mod
from clipper.db.models import Clip, ClipStatus, Source
from clipper.db.session import init_db
from clipper.detect.base import CandidateClip
from clipper.detect.claude import ClaudeDetector
from clipper.detect.mock import MockDetector
from clipper.detect.openai_compat import OpenAICompatDetector
from clipper.detect.service import (
    SourceNotFoundError,
    TranscriptMissingError,
    UnknownProviderError,
    detect_for_source,
    excerpt_for,
    make_detector,
)
from clipper.permissions.service import grant_permission
from clipper.transcribe.base import Segment, Transcript
from clipper.transcribe.store import save_transcript

# A transcript whose segments span 0..75 s — long enough that MockDetector's
# 20–60 s candidates stay within a 75 s source.
_SEGMENTS = [
    Segment(0.0, 6.0, "Welcome to the show, today we have a great guest."),
    Segment(6.0, 30.0, "Here is a genuinely interesting story about the early days."),
    Segment(30.0, 75.0, "And then came the surprising twist that changed everything."),
]
_SOURCE_DURATION = 75.0


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


def _seed_source_with_transcript(
    session: Session, tmp_path: Path, *, with_transcript: bool = True
) -> int:
    """Seed creator + active permission + a Source; optionally write its transcript.

    Returns the source id. When ``with_transcript`` the transcript JSON is
    written under ``tmp_path`` and recorded on the Source (mirroring what ingest
    does), so detection has a real file to load.
    """
    auth = tmp_path / "consent.pdf"
    auth.write_text("signed")
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")

    creator = create_creator(session, name="Authorized Owner")
    session.flush()
    grant_permission(session, creator.id, "youtube", auth)
    source = register_source(session, creator_id=creator.id, file_path=video)
    source.duration_seconds = _SOURCE_DURATION
    if with_transcript:
        path = tmp_path / "transcript.json"
        save_transcript(Transcript(segments=_SEGMENTS, language="en"), path)
        source.transcript_path = str(path)
    session.flush()
    return source.id


# --- excerpt_for: the locally derived excerpt helper --------------------------


def test_excerpt_for_concatenates_overlapping_segments_excludes_others() -> None:
    segments = [
        Segment(0.0, 10.0, "first"),
        Segment(10.0, 20.0, "second"),
        Segment(20.0, 30.0, "third"),
    ]
    # Window [12, 25] overlaps the 2nd and 3rd segments only.
    assert excerpt_for(segments, 12.0, 25.0) == "second third"
    # Window fully inside the first segment -> just that segment.
    assert excerpt_for(segments, 1.0, 5.0) == "first"


def test_excerpt_for_touching_boundary_is_not_included() -> None:
    """A segment that merely abuts the window edge (seg.end == start) is excluded."""
    segments = [Segment(0.0, 10.0, "before"), Segment(10.0, 20.0, "inside")]
    # Window starts exactly where the first segment ends -> only "inside".
    assert excerpt_for(segments, 10.0, 18.0) == "inside"


def test_excerpt_for_no_overlap_is_empty() -> None:
    segments = [Segment(0.0, 10.0, "alpha")]
    assert excerpt_for(segments, 20.0, 30.0) == ""


# --- detect_for_source: persistence happy path --------------------------------


def test_detect_for_source_persists_pending_clips_with_populated_fields(
    engine: Engine, tmp_path: Path
) -> None:
    with Session(engine) as session:
        source_id = _seed_source_with_transcript(session, tmp_path)

        clips = detect_for_source(session, source_id, detector=MockDetector(), max_clips=3)
        session.commit()

        assert 1 <= len(clips) <= 3
        # Everything persisted is a Clip row with a primary key.
        persisted = list(session.scalars(select(Clip).where(Clip.source_id == source_id)))
        assert len(persisted) == len(clips)

        for clip in persisted:
            assert clip.id is not None
            assert clip.status is ClipStatus.pending
            assert clip.score is not None and 0.0 <= clip.score <= 1.0
            assert clip.reason
            assert clip.title
            # Excerpt is derived locally and non-empty for an in-bounds clip.
            assert clip.transcript_excerpt
            assert isinstance(clip.hashtags, list)
            # All times lie within [0, source.duration_seconds].
            assert 0.0 <= clip.start_seconds < clip.end_seconds <= _SOURCE_DURATION
            # Render is a later phase — no output path yet.
            assert clip.output_path is None


def test_detect_for_source_excerpt_matches_local_derivation(engine: Engine, tmp_path: Path) -> None:
    """The persisted excerpt is exactly what `excerpt_for` derives from the transcript."""
    with Session(engine) as session:
        source_id = _seed_source_with_transcript(session, tmp_path)
        clips = detect_for_source(session, source_id, detector=MockDetector(), max_clips=2)
        for clip in clips:
            assert isinstance(clip, Clip)
            expected = excerpt_for(_SEGMENTS, clip.start_seconds, clip.end_seconds)
            assert clip.transcript_excerpt == expected


def test_detect_for_source_defaults_max_clips_from_settings(engine: Engine, tmp_path: Path) -> None:
    """Omitting max_clips falls back to Settings.detector_max_clips (5)."""
    with Session(engine) as session:
        source_id = _seed_source_with_transcript(session, tmp_path)
        clips = detect_for_source(session, source_id, detector=MockDetector())
        # The 3-segment transcript yields 3 candidates, under the default cap of 5.
        assert 1 <= len(clips) <= get_settings().detector_max_clips


# --- detect_for_source: refusals & eval mode ----------------------------------


def test_detect_for_source_refuses_when_no_transcript_and_persists_nothing(
    engine: Engine, tmp_path: Path
) -> None:
    with Session(engine) as session:
        source_id = _seed_source_with_transcript(session, tmp_path, with_transcript=False)

        with pytest.raises(TranscriptMissingError):
            detect_for_source(session, source_id, detector=MockDetector())
        session.commit()

        assert session.scalar(select(func.count()).select_from(Clip)) == 0


def test_detect_for_source_raises_for_unknown_source(engine: Engine) -> None:
    with Session(engine) as session:
        with pytest.raises(SourceNotFoundError):
            detect_for_source(session, 999, detector=MockDetector())


def test_detect_for_source_persist_false_returns_candidates_and_writes_nothing(
    engine: Engine, tmp_path: Path
) -> None:
    with Session(engine) as session:
        source_id = _seed_source_with_transcript(session, tmp_path)

        result = detect_for_source(
            session, source_id, detector=MockDetector(), max_clips=3, persist=False
        )
        session.commit()

        assert len(result) >= 1
        assert all(isinstance(c, CandidateClip) for c in result)
        assert session.scalar(select(func.count()).select_from(Clip)) == 0


class _OutOfBoundsDetector:
    """A detector that emits candidates straddling/exceeding the source duration.

    Used to prove the persistence invariant: with the source duration set to
    50 s below, the first clip is in bounds, the second overruns the end (and is
    clamped to it), and the third lies entirely past it (and is skipped).
    """

    def detect(self, transcript: Transcript, *, max_clips: int = 5) -> list[CandidateClip]:
        return [
            CandidateClip(start=10.0, end=40.0, score=0.9, reason="in bounds", title="a"),
            CandidateClip(start=30.0, end=90.0, score=0.7, reason="overruns end", title="b"),
            CandidateClip(start=60.0, end=120.0, score=0.5, reason="fully past end", title="c"),
        ]


def test_detect_for_source_clamps_times_to_duration_and_skips_out_of_bounds(
    engine: Engine, tmp_path: Path
) -> None:
    """Persisted rows are clamped to [0, duration]; a fully-out-of-bounds clip is skipped."""
    with Session(engine) as session:
        source_id = _seed_source_with_transcript(session, tmp_path)
        source = session.get(Source, source_id)
        assert source is not None
        source.duration_seconds = 50.0  # shorter than candidates "b" and "c"
        session.flush()

        clips = detect_for_source(session, source_id, detector=_OutOfBoundsDetector())
        session.commit()

        persisted = list(session.scalars(select(Clip).where(Clip.source_id == source_id)))
        # "c" (60..120) is entirely past the 50 s source → skipped. Two rows remain.
        assert {c.title for c in persisted} == {"a", "b"}
        by_title = {c.title: c for c in persisted}
        # "a" is wholly in bounds → unchanged.
        assert (by_title["a"].start_seconds, by_title["a"].end_seconds) == (10.0, 40.0)
        # "b" overran the end → end clamped down to the duration.
        assert (by_title["b"].start_seconds, by_title["b"].end_seconds) == (30.0, 50.0)
        # Every persisted clip respects the [0, duration] invariant.
        for clip in persisted:
            assert 0.0 <= clip.start_seconds < clip.end_seconds <= 50.0
        # The clamped "b" excerpt is derived from the clamped window, not the raw end.
        assert by_title["b"].transcript_excerpt == excerpt_for(_SEGMENTS, 30.0, 50.0)
        assert len(clips) == 2


def test_detect_for_source_persists_as_is_when_duration_unknown(
    engine: Engine, tmp_path: Path
) -> None:
    """With Source.duration_seconds None, times are persisted unchanged (no clamp)."""
    with Session(engine) as session:
        source_id = _seed_source_with_transcript(session, tmp_path)
        source = session.get(Source, source_id)
        assert source is not None
        source.duration_seconds = None
        session.flush()

        clips = detect_for_source(session, source_id, detector=_OutOfBoundsDetector())
        session.commit()

        persisted = list(session.scalars(select(Clip).where(Clip.source_id == source_id)))
        # No clamp, no skip — all three candidates persist with their raw times.
        assert {c.title for c in persisted} == {"a", "b", "c"}
        by_title = {c.title: c for c in persisted}
        assert (by_title["c"].start_seconds, by_title["c"].end_seconds) == (60.0, 120.0)
        assert len(clips) == 3


# --- provider selector --------------------------------------------------------


def test_make_detector_resolves_each_provider_name() -> None:
    assert isinstance(make_detector("mock"), MockDetector)
    assert isinstance(make_detector("claude"), ClaudeDetector)
    assert isinstance(make_detector("openai-compat"), OpenAICompatDetector)


def test_make_detector_rejects_unknown_provider() -> None:
    with pytest.raises(UnknownProviderError):
        make_detector("gemini")


# --- CLI layer ----------------------------------------------------------------

runner = CliRunner()


@pytest.fixture
def storage_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the configured DB at tmp_path and reset the cached settings/engine."""
    monkeypatch.setenv("CLIPPER_STORAGE_DIR", str(tmp_path / "storage"))
    get_settings.cache_clear()
    session_mod.get_engine.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
    session_mod.get_engine.cache_clear()


def _only_id(pattern: str, text: str) -> int:
    match = re.search(pattern, text)
    assert match is not None, f"could not find id in: {text!r}"
    return int(match.group(1))


def _seed_via_cli(storage_in_tmp: Path, *, with_transcript: bool) -> int:
    """Create creator+permission+source through the CLI; optionally attach a transcript."""
    add = runner.invoke(app, ["creator", "add", "--name", "Owner"])
    creator_id = _only_id(r"Created creator (\d+)", add.output)
    auth = storage_in_tmp / "consent.pdf"
    auth.write_text("signed")
    grant = runner.invoke(
        app,
        [
            "permission",
            "grant",
            "--creator",
            str(creator_id),
            "--scope",
            "yt",
            "--auth-file",
            str(auth),
        ],
    )
    assert grant.exit_code == 0, grant.output
    video = storage_in_tmp / "talk.mp4"
    video.write_bytes(b"\x00\x00")
    add_src = runner.invoke(
        app, ["source", "add", "--file", str(video), "--creator", str(creator_id)]
    )
    assert add_src.exit_code == 0, add_src.output
    source_id = _only_id(r"Created source (\d+)", add_src.output)

    with Session(session_mod.get_engine()) as session:
        source = session.get(Source, source_id)
        assert source is not None
        source.duration_seconds = _SOURCE_DURATION
        if with_transcript:
            path = storage_in_tmp / "transcript.json"
            save_transcript(Transcript(segments=_SEGMENTS, language="en"), path)
            source.transcript_path = str(path)
        session.commit()
    return source_id


def test_cli_detect_mock_persists_pending_clips_and_prints_summary(
    storage_in_tmp: Path,
) -> None:
    source_id = _seed_via_cli(storage_in_tmp, with_transcript=True)

    result = runner.invoke(app, ["detect", str(source_id), "--mock"])
    assert result.exit_code == 0, result.output
    assert "candidate clips" in result.output
    assert "provider=mock" in result.output

    with Session(session_mod.get_engine()) as session:
        clips = list(session.scalars(select(Clip).where(Clip.source_id == source_id)))
        assert len(clips) >= 1
        assert all(c.status is ClipStatus.pending for c in clips)
        assert all(c.transcript_excerpt for c in clips)


def test_cli_detect_refuses_when_no_transcript_nonzero_exit(storage_in_tmp: Path) -> None:
    source_id = _seed_via_cli(storage_in_tmp, with_transcript=False)

    result = runner.invoke(app, ["detect", str(source_id), "--mock"])
    assert result.exit_code != 0

    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Clip)) == 0
