"""Transcript ⇄ JSON persistence.

Transcripts are written as plain, portable JSON (language + a list of
segments) under the storage dir and recorded on the owning `Source` so the
detection phase can load them back without re-transcribing.
"""

from __future__ import annotations

import json
from pathlib import Path

from clipper.db.models import Source
from clipper.transcribe.base import Segment, Transcript


def save_transcript(transcript: Transcript, path: Path) -> Path:
    """Write `transcript` to `path` as JSON (creating parent dirs); return `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "language": transcript.language,
        "segments": [
            {"start": seg.start, "end": seg.end, "text": seg.text} for seg in transcript.segments
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_transcript(path: Path) -> Transcript:
    """Read a `Transcript` back from the JSON written by `save_transcript`."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    segments = [
        Segment(start=seg["start"], end=seg["end"], text=seg["text"]) for seg in payload["segments"]
    ]
    return Transcript(segments=segments, language=payload.get("language"))


def persist_transcript(source: Source, transcript: Transcript, *, storage_dir: Path) -> Path:
    """Save `transcript` under `storage_dir/transcripts/<id>.json` and record it.

    Writes the JSON, sets `source.transcript_path` to the written path, and
    returns it.
    """
    path = storage_dir / "transcripts" / f"{source.id}.json"
    save_transcript(transcript, path)
    source.transcript_path = str(path)
    return path
