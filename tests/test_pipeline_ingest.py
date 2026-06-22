"""Tests for the ingest pipeline wiring (T5).

Unit coverage runs ``run_ingest`` against an in-memory engine (never the real
``storage/clipper.db``) with a mock transcriber and fake ``probe_fn``/
``extract_fn``, so no ffmpeg or Whisper is needed: it asserts stage order,
progress/status transitions, the permission gate, and error capture. Storage is
redirected to ``tmp_path`` (the stages write a work WAV + the transcript JSON),
so nothing touches the developer's real storage dir. An end-to-end integration
test builds a short spoken clip and runs the real pipeline; it skips cleanly
when ffmpeg / faster-whisper / macOS `say` are unavailable.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from clipper.catalog import create_creator, register_source
from clipper.config import get_settings
from clipper.db.models import Job, JobStatus, PermissionStatus, Source
from clipper.db.session import init_db
from clipper.media import ffmpeg
from clipper.permissions.service import PermissionRequiredError, grant_permission
from clipper.pipeline.jobs import SourceNotFoundError, run_ingest
from clipper.pipeline.stages import STAGE_ORDER
from clipper.transcribe.base import Segment, Transcript

_HAS_WHISPER = importlib.util.find_spec("faster_whisper") is not None
_HAS_SAY = shutil.which("say") is not None


# --- fixtures -----------------------------------------------------------------


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


@pytest.fixture
def storage_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the configured storage dir to tmp_path and reset the cache.

    ``run_ingest`` reads ``get_settings().storage_dir`` for the work WAV and the
    transcript JSON, so without this the stages would write under the real
    ``storage/``.
    """
    storage = tmp_path / "storage"
    monkeypatch.setenv("CLIPPER_STORAGE_DIR", str(storage))
    get_settings.cache_clear()
    yield storage
    get_settings.cache_clear()


def _seed_source(session: Session, video: Path, *, revoked: bool = False) -> int:
    """Seed creator + (active|revoked) permission + a registered Source; return its id.

    A revoked permission still lets the Source be *registered* here (we flip the
    status after registration) so the ingest-time gate can be exercised.
    """
    auth = video.parent / "consent.pdf"
    auth.write_text("signed")
    creator = create_creator(session, name="Authorized Owner")
    session.flush()
    record = grant_permission(session, creator.id, "youtube", auth)
    source = register_source(session, creator_id=creator.id, file_path=video)
    if revoked:
        record.status = PermissionStatus.revoked
    session.flush()
    return source.id


def _fake_probe(calls: list[str]):
    """A probe_fn that records the call and returns a fixed MediaInfo-shaped result."""
    from clipper.media.probe import MediaInfo

    def _probe(path: Path) -> MediaInfo:
        calls.append("probe")
        return MediaInfo(duration=12.5, width=1920, height=1080)

    return _probe


def _fake_extract(calls: list[str]):
    """An extract_fn that records the call and writes a dummy WAV at dst."""

    def _extract(src: Path, dst: Path) -> Path:
        calls.append("audio")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
        return dst

    return _extract


class _MockTranscriber:
    """A `Transcriber` returning a fixed transcript; records its call."""

    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def transcribe(self, audio_path: Path) -> Transcript:
        self._calls.append("transcribe")
        return Transcript(
            segments=[
                Segment(0.0, 6.0, "Hello and welcome."),
                Segment(6.0, 12.5, "Here is the interesting part."),
            ],
            language="en",
        )


# --- unit: happy path ---------------------------------------------------------


def test_run_ingest_runs_stages_in_order_and_populates_source(
    engine: Engine, storage_in_tmp: Path, tmp_path: Path
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")
    calls: list[str] = []

    with Session(engine) as session:
        source_id = _seed_source(session, video)

        job = run_ingest(
            session,
            source_id,
            transcriber=_MockTranscriber(calls),
            probe_fn=_fake_probe(calls),
            extract_fn=_fake_extract(calls),
        )
        session.commit()

        # A Job was created, of the right kind, and finished cleanly.
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        assert job.id is not None
        assert job.kind == "ingest"
        assert job.status is JobStatus.done
        assert job.progress == 1.0
        assert job.error is None

        # The stages ran in the documented order.
        assert calls == ["probe", "audio", "transcribe"]
        assert list(STAGE_ORDER) == ["probe", "audio", "transcribe", "persist"]

        # The Source was populated end to end.
        source = session.get(Source, source_id)
        assert source is not None
        assert source.duration_seconds == 12.5
        assert source.width == 1920
        assert source.height == 1080
        assert source.transcript_path is not None
        assert Path(source.transcript_path).exists()


def test_run_ingest_progress_advances_monotonically(
    engine: Engine, storage_in_tmp: Path, tmp_path: Path
) -> None:
    """Progress is captured at each stage boundary and only ever increases.

    ``run_ingest`` flushes the Job before the stages run, so the injected stage
    callables can read its live ``progress`` from the session — the sequence
    reflects how a poller (T13) would observe the bar advance.
    """
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")
    calls: list[str] = []
    seen: list[float] = []

    def _live_progress() -> float:
        job = session.scalars(select(Job).order_by(Job.id.desc())).first()
        assert job is not None
        return job.progress

    def _probe(path: Path):
        from clipper.media.probe import MediaInfo

        calls.append("probe")
        seen.append(_live_progress())  # 0.0 — nothing done yet
        return MediaInfo(duration=12.5, width=1920, height=1080)

    def _extract(src: Path, dst: Path) -> Path:
        calls.append("audio")
        seen.append(_live_progress())  # 0.25 — probe done
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"RIFF")
        return dst

    class _Transcriber:
        def transcribe(self, audio_path: Path) -> Transcript:
            calls.append("transcribe")
            seen.append(_live_progress())  # 0.5 — audio done
            return Transcript(segments=[Segment(0.0, 1.0, "hi")], language="en")

    with Session(engine) as session:
        source_id = _seed_source(session, video)
        job = run_ingest(
            session,
            source_id,
            transcriber=_Transcriber(),
            probe_fn=_probe,
            extract_fn=_extract,
        )

        assert job.status is JobStatus.done
        assert calls == ["probe", "audio", "transcribe"]
        assert seen == [0.0, 0.25, 0.5]
        assert seen == sorted(seen)  # monotonic stage boundaries
        assert job.progress == 1.0


# --- unit: stage failure ------------------------------------------------------


def test_run_ingest_captures_stage_failure_without_raising(
    engine: Engine, storage_in_tmp: Path, tmp_path: Path
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")
    calls: list[str] = []

    def _boom_extract(src: Path, dst: Path) -> Path:
        raise RuntimeError("ffmpeg blew up")

    with Session(engine) as session:
        source_id = _seed_source(session, video)

        # Must NOT raise — the failure is captured onto the Job.
        job = run_ingest(
            session,
            source_id,
            transcriber=_MockTranscriber(calls),
            probe_fn=_fake_probe(calls),
            extract_fn=_boom_extract,
        )
        session.commit()

        assert job.status is JobStatus.error
        assert job.stage == "audio"
        assert job.error is not None
        assert "ffmpeg blew up" in job.error
        # The failing stage ran after probe; transcribe never did.
        assert calls == ["probe"]

        # The Source's downstream fields were never populated.
        source = session.get(Source, source_id)
        assert source is not None
        assert source.transcript_path is None


# --- unit: the gate -----------------------------------------------------------


def test_run_ingest_refuses_when_permission_revoked_and_leaves_no_done_job(
    engine: Engine, storage_in_tmp: Path, tmp_path: Path
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")
    calls: list[str] = []

    with Session(engine) as session:
        source_id = _seed_source(session, video, revoked=True)

        with pytest.raises(PermissionRequiredError):
            run_ingest(
                session,
                source_id,
                transcriber=_MockTranscriber(calls),
                probe_fn=_fake_probe(calls),
                extract_fn=_fake_extract(calls),
            )
        session.commit()

        # The gate fired before any Job was created — none, let alone a `done` one.
        assert calls == []
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert (
            session.scalar(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.done)
            )
            == 0
        )


def test_run_ingest_refuses_when_no_permission_at_all(
    engine: Engine, storage_in_tmp: Path, tmp_path: Path
) -> None:
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"\x00\x00")

    with Session(engine) as session:
        # Register the source under an active permission, then delete the record
        # so that at ingest time the creator has none.
        auth = tmp_path / "consent.pdf"
        auth.write_text("signed")
        creator = create_creator(session, name="Owner")
        session.flush()
        record = grant_permission(session, creator.id, "youtube", auth)
        source = register_source(session, creator_id=creator.id, file_path=video)
        source_id = source.id
        record.status = PermissionStatus.revoked
        session.flush()

        with pytest.raises(PermissionRequiredError):
            run_ingest(session, source_id, transcriber=_MockTranscriber([]))
        session.commit()

        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_run_ingest_raises_for_unknown_source(engine: Engine, storage_in_tmp: Path) -> None:
    with Session(engine) as session:
        with pytest.raises(SourceNotFoundError):
            run_ingest(session, 999, transcriber=_MockTranscriber([]))


# --- integration: real probe + extract + transcribe --------------------------


@pytest.mark.integration
@pytest.mark.skipif(not ffmpeg.ffmpeg_available(), reason="ffmpeg not available")
@pytest.mark.skipif(not _HAS_WHISPER, reason="faster-whisper not installed")
@pytest.mark.skipif(not _HAS_SAY, reason="macOS `say` not available")
def test_run_ingest_end_to_end_on_spoken_clip(
    engine: Engine, storage_in_tmp: Path, tmp_path: Path
) -> None:
    """End to end: a ~6 s clip with a real speech track ingests to a `done` Job."""
    import subprocess

    from clipper.transcribe.store import load_transcript
    from clipper.transcribe.whisper_local import WhisperTranscriber

    # A real speech track (macOS `say`) muxed with a lavfi video -> a tiny clip.
    aiff = tmp_path / "speech.aiff"
    subprocess.run(
        ["say", "-o", str(aiff), "The quick brown fox jumps over the lazy dog."],
        check=True,
        capture_output=True,
    )
    clip = tmp_path / "clip.mp4"
    ffmpeg.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=6:size=320x240:rate=30",
            "-i",
            str(aiff),
            "-shortest",
            str(clip),
        ]
    )

    with Session(engine) as session:
        source_id = _seed_source(session, clip)

        job = run_ingest(session, source_id, transcriber=WhisperTranscriber(model="tiny"))
        session.commit()

        assert job.status is JobStatus.done, job.error
        assert job.progress == 1.0

        source = session.get(Source, source_id)
        assert source is not None
        assert source.duration_seconds is not None and source.duration_seconds > 0
        assert source.width == 320
        assert source.height == 240

        assert source.transcript_path is not None
        transcript_path = Path(source.transcript_path)
        assert transcript_path.exists()
        transcript = load_transcript(transcript_path)
        assert len(transcript.segments) >= 1
