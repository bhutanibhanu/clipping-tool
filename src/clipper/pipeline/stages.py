"""Ingest stages: the ordered probe -> audio -> transcribe -> persist sequence.

Each stage is a small named step that mutates the in-flight `Source` (and the
filesystem under the storage dir); `run_stages` walks them in order, advancing
`Job.stage`/`Job.progress` as each completes and surfacing the first failure to
the caller. The media/transcription dependencies are passed in (not imported at
call time) so the sequence runs under unit tests with fakes — no ffmpeg or
Whisper needed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from clipper.db.models import Job, Source
from clipper.transcribe.base import Transcriber, Transcript
from clipper.transcribe.store import persist_transcript

# Injectable dependency signatures (the real ones are `probe`, `extract_audio`).
ProbeFn = Callable[[Path], object]
ExtractFn = Callable[[Path, Path], Path]


@dataclass(frozen=True)
class IngestDeps:
    """The three swappable dependencies the ingest stages need.

    Bundling them keeps `run_stages` signature small and lets callers (and
    tests) build the set once. `probe` returns a `MediaInfo`-shaped object
    (duration/width/height); `extract` writes a WAV and returns its path.
    """

    probe: ProbeFn
    extract: ExtractFn
    transcriber: Transcriber


# The canonical stage order, recorded on the Job as each completes. Progress is
# a monotonic fraction so a UI/poller (T13) can render a determinate bar.
STAGE_ORDER: tuple[str, ...] = ("probe", "audio", "transcribe", "persist")
_PROGRESS: dict[str, float] = {"probe": 0.25, "audio": 0.5, "transcribe": 0.75, "persist": 1.0}


def run_stages(
    job: Job,
    source: Source,
    deps: IngestDeps,
    *,
    storage_dir: Path,
) -> None:
    """Run probe -> audio -> transcribe -> persist for `source`, advancing `job`.

    On entry to each stage `job.stage` is set; on completion `job.progress` is
    bumped to that stage's fraction. Any exception propagates to the caller
    (`run_ingest`), which records it against the Job — this function does not
    swallow errors, so the failing `job.stage` is left pointing at the step that
    raised.
    """
    src_path = Path(source.file_path)

    # 1. probe: container/stream facts onto the Source.
    job.stage = "probe"
    info = deps.probe(src_path)
    source.duration_seconds = float(info.duration)  # type: ignore[attr-defined]
    source.width = int(info.width)  # type: ignore[attr-defined]
    source.height = int(info.height)  # type: ignore[attr-defined]
    job.progress = _PROGRESS["probe"]

    # 2. audio: a transcription-ready 16 kHz mono WAV under storage/work/<id>/.
    job.stage = "audio"
    wav = storage_dir / "work" / str(source.id) / "audio.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav = deps.extract(src_path, wav)
    job.progress = _PROGRESS["audio"]

    # 3. transcribe: segment-timestamped text (CPU Whisper on the Air).
    job.stage = "transcribe"
    transcript: Transcript = deps.transcriber.transcribe(wav)
    job.progress = _PROGRESS["transcribe"]

    # 4. persist: write the transcript JSON and record it on the Source.
    job.stage = "persist"
    persist_transcript(source, transcript, storage_dir=storage_dir)
    job.progress = _PROGRESS["persist"]
