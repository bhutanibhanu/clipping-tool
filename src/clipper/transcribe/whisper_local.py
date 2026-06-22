"""faster-whisper implementation of the `Transcriber` protocol.

CPU-only on the Mac (the 8 GB M1 Air target); model size and compute type
come from `Settings` (`small`/`int8` defaults). faster-whisper is an optional
extra, so the import is deferred to construction time — importing this module
must not fail when the `[transcribe]` extra is absent.
"""

from __future__ import annotations

from pathlib import Path

from clipper.config import get_settings
from clipper.transcribe.base import Segment, Transcript


class TranscriberUnavailableError(RuntimeError):
    """Raised when the optional ``faster-whisper`` engine is not installed.

    A specific subclass (rather than a bare ``RuntimeError``) so the CLI can
    catch *this* and exit cleanly without swallowing unrelated runtime errors.
    """


def _segments_from_whisper(segments_iter: object) -> list[Segment]:
    """Map faster-whisper segments to `Segment`s, dropping blank text.

    Pure helper (no model needed) so the empty/whitespace-only filtering is
    unit-testable: any segment whose ``text`` strips to empty is skipped, and
    the kept text is stored already stripped.
    """
    segments: list[Segment] = []
    for seg in segments_iter:  # type: ignore[attr-defined]
        text = seg.text.strip()
        if not text:
            continue
        segments.append(Segment(start=seg.start, end=seg.end, text=text))
    return segments


class WhisperTranscriber:
    """Transcribe local audio with faster-whisper (satisfies `Transcriber`)."""

    def __init__(self, model: str | None = None, compute_type: str | None = None) -> None:
        settings = get_settings()
        self.model = model or settings.whisper_model
        self.compute_type = compute_type or settings.whisper_compute_type
        # Fail loudly and early if the optional extra is missing, but only when
        # someone actually constructs a transcriber (not on module import).
        self._whisper_model_cls = _load_whisper_model_cls()

    def transcribe(self, audio_path: Path) -> Transcript:
        """Return a timestamped `Transcript` for the audio at `audio_path`."""
        model = self._whisper_model_cls(self.model, device="cpu", compute_type=self.compute_type)
        segments_iter, info = model.transcribe(str(audio_path))
        return Transcript(segments=_segments_from_whisper(segments_iter), language=info.language)


def _load_whisper_model_cls() -> type:
    """Import faster-whisper lazily; raise a clear error if it is absent."""
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise TranscriberUnavailableError(
            "faster-whisper not installed; pip install -e '.[transcribe]'"
        ) from exc
    return WhisperModel
