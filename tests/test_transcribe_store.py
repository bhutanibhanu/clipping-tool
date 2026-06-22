from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clipper.db.models import Creator, PermissionRecord, Source
from clipper.db.session import init_db
from clipper.transcribe import whisper_local
from clipper.transcribe.base import Transcriber, Transcript
from clipper.transcribe.store import load_transcript, persist_transcript, save_transcript
from clipper.transcribe.whisper_local import WhisperTranscriber


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
        raise RuntimeError("faster-whisper not installed; pip install -e '.[transcribe]'")

    monkeypatch.setattr(whisper_local, "_load_whisper_model_cls", _boom)
    with pytest.raises(RuntimeError, match="faster-whisper not installed"):
        WhisperTranscriber()
