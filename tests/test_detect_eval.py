"""Tests for the eval harness (T5): the pure report formatter + `detect --eval`.

`format_eval_report` is exercised directly against hand-built ``CandidateClip``s
and a small transcript (no network, no DB), asserting the header carries the
provider + ``PROMPT_VERSION`` and that every candidate renders a ``mm:ss``
timecode, its score, title, and the locally derived excerpt. The CLI layer is
driven through typer's ``CliRunner`` with storage redirected to ``tmp_path``
(reusing T4's seed-via-CLI pattern): ``clipper detect <id> --eval --mock`` must
print the report AND leave **zero** ``Clip`` rows behind, since repeated
prompt-iteration eval runs must never accumulate pending clips.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from clipper.cli import app
from clipper.config import get_settings
from clipper.db import session as session_mod
from clipper.db.models import Clip, Source
from clipper.detect.base import CandidateClip
from clipper.detect.eval import format_eval_report
from clipper.detect.prompt import PROMPT_VERSION
from clipper.transcribe.base import Segment, Transcript
from clipper.transcribe.store import save_transcript

# A transcript spanning 0..300 s so the candidates below sit on real text.
_SEGMENTS = [
    Segment(0.0, 65.0, "The single biggest mistake people make when they start out."),
    Segment(65.0, 130.0, "Here is the counterintuitive lesson that took me ten years."),
    Segment(130.0, 200.0, "And that is exactly why most advice you hear is wrong."),
    Segment(200.0, 300.0, "One last thing nobody tells you about doing this well."),
]
_SOURCE_DURATION = 300.0


def _candidates() -> list[CandidateClip]:
    """Five well-formed, descending-score candidates (MockDetector-shaped)."""
    return [
        CandidateClip(
            start=0.0,
            end=65.0,
            score=0.91,
            reason="Hook + payload: opens on the biggest mistake.",
            title="The #1 Beginner Mistake",
            description="cap",
            hashtags=["#advice"],
        ),
        CandidateClip(
            start=65.0,
            end=130.0,
            score=0.80,
            reason="Self-contained insight that lands alone.",
            title="The Counterintuitive Lesson",
        ),
        CandidateClip(
            start=130.0,
            end=200.0,
            score=0.72,
            reason="Payload: a strong contrarian opinion.",
            title="Why Most Advice Is Wrong",
        ),
        CandidateClip(
            start=200.0,
            end=260.0,
            score=0.66,
            reason="Length-fit closer with a clear takeaway.",
            title="The Thing Nobody Tells You",
        ),
        CandidateClip(
            start=30.0,
            end=95.0,
            score=0.55,
            reason="Weaker hook but self-contained.",
            title="A Second Look",
        ),
    ]


# --- format_eval_report: the pure formatter -----------------------------------


def test_format_eval_report_renders_header_and_rows() -> None:
    candidates = _candidates()
    report = format_eval_report(
        candidates,
        _SEGMENTS,
        provider="mock",
        model="mock",
        prompt_version=PROMPT_VERSION,
        source_id=42,
    )

    # Header is attributable: provider + prompt_version + source id + count.
    first_line = report.splitlines()[0]
    assert "provider=mock" in first_line
    assert f"prompt_version={PROMPT_VERSION}" in first_line
    assert "source=42" in first_line
    assert "candidates=5" in first_line

    # One numbered block per candidate (rank markers #1..#5).
    for rank in range(1, 6):
        assert f"#{rank} " in report

    # Each candidate renders a mm:ss timecode, its score, title, and excerpt text.
    assert "00:00-01:05" in report  # 0s -> 65s
    assert "01:05-02:10" in report  # 65s -> 130s
    assert "score=0.91" in report
    assert "The #1 Beginner Mistake" in report
    assert "Why Most Advice Is Wrong" in report
    # Derived excerpt (from _SEGMENTS) appears, not echoed by any model.
    assert "biggest mistake people make" in report
    assert "counterintuitive lesson" in report


def test_format_eval_report_row_count_matches_candidates() -> None:
    """A 3-candidate input renders exactly 3 ranked blocks (N, not a fixed 5)."""
    three = _candidates()[:3]
    report = format_eval_report(
        three,
        _SEGMENTS,
        provider="claude",
        model="claude-opus-4-8",
        prompt_version=PROMPT_VERSION,
        source_id=7,
    )
    ranks = re.findall(r"^#(\d+) ", report, flags=re.MULTILINE)
    assert ranks == ["1", "2", "3"]
    assert "candidates=3" in report.splitlines()[0]
    assert "provider=claude" in report.splitlines()[0]


def test_format_eval_report_truncates_long_excerpt() -> None:
    """A very long overlapping segment is truncated with an ellipsis to stay scannable."""
    long_text = "word " * 200  # ~1000 chars, well over the ~200-char cap.
    segments = [Segment(0.0, 60.0, long_text)]
    cand = CandidateClip(start=0.0, end=60.0, score=0.5, reason="r", title="t")
    report = format_eval_report(
        [cand],
        segments,
        provider="mock",
        model="mock",
        prompt_version=PROMPT_VERSION,
        source_id=1,
    )
    excerpt_line = next(line for line in report.splitlines() if line.strip().startswith("excerpt:"))
    assert "…" in excerpt_line
    # The truncated excerpt portion stays within the cap (+ a little label slack).
    assert len(excerpt_line) < 230


def test_format_eval_report_handles_no_candidates() -> None:
    report = format_eval_report(
        [],
        _SEGMENTS,
        provider="mock",
        model="mock",
        prompt_version=PROMPT_VERSION,
        source_id=1,
    )
    assert "candidates=0" in report
    assert "(no candidates)" in report


# --- CLI: `clipper detect --eval` persists nothing ----------------------------

runner = CliRunner()

_SOURCE_DURATION_CLI = _SOURCE_DURATION


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
        source.duration_seconds = _SOURCE_DURATION_CLI
        if with_transcript:
            path = storage_in_tmp / "transcript.json"
            save_transcript(Transcript(segments=_SEGMENTS, language="en"), path)
            source.transcript_path = str(path)
        session.commit()
    return source_id


def test_cli_detect_eval_prints_report_and_persists_zero_clips(storage_in_tmp: Path) -> None:
    source_id = _seed_via_cli(storage_in_tmp, with_transcript=True)

    result = runner.invoke(app, ["detect", str(source_id), "--eval", "--mock"])
    assert result.exit_code == 0, result.output

    # The eval report header + its attribution show up...
    assert "Eval report" in result.output
    assert "provider=mock" in result.output
    assert f"prompt_version={PROMPT_VERSION}" in result.output
    assert f"source={source_id}" in result.output
    # ...and MockDetector's first candidate title ("Clip 1") renders.
    assert "Clip 1" in result.output
    # The T4 persist-mode summary line must NOT appear on the eval path.
    assert "candidate clips for source" not in result.output

    # Crucially: --eval persists ZERO Clip rows (no accumulation across runs).
    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Clip)) == 0


def test_cli_detect_eval_repeated_runs_still_persist_zero(storage_in_tmp: Path) -> None:
    """Re-running the eval (the prompt-iteration loop) never accumulates clips."""
    source_id = _seed_via_cli(storage_in_tmp, with_transcript=True)

    for _ in range(3):
        result = runner.invoke(app, ["detect", str(source_id), "--eval", "--mock"])
        assert result.exit_code == 0, result.output

    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Clip)) == 0


def test_cli_detect_eval_refuses_when_no_transcript_nonzero_exit(storage_in_tmp: Path) -> None:
    source_id = _seed_via_cli(storage_in_tmp, with_transcript=False)

    result = runner.invoke(app, ["detect", str(source_id), "--eval", "--mock"])
    assert result.exit_code != 0

    with Session(session_mod.get_engine()) as session:
        assert session.scalar(select(func.count()).select_from(Clip)) == 0
