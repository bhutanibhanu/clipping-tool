from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.db.models import Creator, PermissionRecord, Source
from clipper.db.session import init_db
from clipper.transcribe import whisper_local
from clipper.transcribe.base import Transcriber, Transcript
from clipper.transcribe.store import load_transcript, persist_transcript, save_transcript
from clipper.transcribe.whisper_local import (
    TranscriberUnavailableError,
    WhisperTranscriber,
    _segments_from_whisper,
)


@dataclass
class _FakeSeg:
    """Minimal stand-in for a faster-whisper segment (just the fields we read)."""

    start: float
    end: float
    text: str


def test_save_load_roundtrip(transcript: Transcript, tmp_path: Path) -> None:
    path = tmp_path / "out" / "transcript.json"
    saved = save_transcript(transcript, path)

    assert saved == path
    assert path.exists()

    loaded = load_transcript(path)
    assert loaded == transcript
    assert loaded.language == "en"
    assert loaded.segments == transcript.segments


def test_persist_transcript_sets_source_path(transcript: Transcript, tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)

    with Session(engine) as s:
        creator = Creator(name="Test Creator")
        perm = PermissionRecord(creator=creator, scope="youtube")
        source = Source(creator=creator, permission=perm, file_path="/tmp/video.mp4")
        s.add_all([creator, perm, source])
        s.commit()

        path = persist_transcript(source, transcript, storage_dir=tmp_path)

        expected = tmp_path / "transcripts" / f"{source.id}.json"
        assert path == expected
        assert path.exists()
        assert source.transcript_path == str(expected)
        # The recorded path round-trips to the same transcript.
        assert load_transcript(Path(source.transcript_path)) == transcript


def test_whisper_transcriber_satisfies_protocol() -> None:
    # Structural check: WhisperTranscriber is a Transcriber without a live model.
    assert isinstance(WhisperTranscriber(model="tiny"), Transcriber)


def test_whisper_raises_clear_error_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> type:
        raise TranscriberUnavailableError(
            "faster-whisper not installed; pip install -e '.[transcribe]'"
        )

    monkeypatch.setattr(whisper_local, "_load_whisper_model_cls", _boom)
    # A specific subclass so the CLI can catch it without swallowing other errors,
    # while staying a RuntimeError for existing callers.
    assert issubclass(TranscriberUnavailableError, RuntimeError)
    with pytest.raises(TranscriberUnavailableError, match="faster-whisper not installed"):
        WhisperTranscriber()


def test_segment_mapping_drops_empty_and_whitespace_text() -> None:
    raw = [
        _FakeSeg(0.0, 1.0, "  hello  "),
        _FakeSeg(1.0, 2.0, "   "),  # whitespace-only -> dropped
        _FakeSeg(2.0, 3.0, ""),  # empty -> dropped
        _FakeSeg(3.0, 4.0, "world"),
    ]
    segments = _segments_from_whisper(iter(raw))

    assert [(s.start, s.end, s.text) for s in segments] == [
        (0.0, 1.0, "hello"),  # text stored stripped
        (3.0, 4.0, "world"),
    ]


def test_segment_mapping_keeps_all_when_none_blank() -> None:
    raw = [_FakeSeg(0.0, 1.0, "a"), _FakeSeg(1.0, 2.0, "b")]
    assert len(_segments_from_whisper(iter(raw))) == 2
