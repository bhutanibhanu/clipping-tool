"""Ingest orchestration: the permission gate, the Job, and error capture.

`run_ingest` is the single synchronous entry point Phase 1 needs: it re-checks
consent at processing time (the gate fires *before* any Job exists, so a refused
ingest leaves nothing behind), then runs the ordered stages as one `Job` with
``concurrency = 1`` — Whisper and ffmpeg never overlap on the 8 GB M1 Air. A
stage failure is captured onto the Job (status/stage/error), not propagated, so
a single bad source can never crash the worker. The async worker + polling that
drives this in the background is a later task (T13); this stays in-process.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from clipper.config import get_settings
from clipper.db.models import Job, JobStatus, Source
from clipper.media.audio import extract_audio
from clipper.media.probe import probe
from clipper.permissions.service import require_permission
from clipper.pipeline.stages import ExtractFn, IngestDeps, ProbeFn, run_stages
from clipper.transcribe.base import Transcriber


class SourceNotFoundError(LookupError):
    """Raised when ``run_ingest`` is given a source id that does not exist."""


def run_ingest(
    session: Session,
    source_id: int,
    *,
    transcriber: Transcriber | None = None,
    probe_fn: ProbeFn | None = None,
    extract_fn: ExtractFn | None = None,
) -> Job:
    """Probe -> extract audio -> transcribe -> persist `source_id` as one Job.

    Looks up the Source (``SourceNotFoundError`` if absent), then enforces the
    consent gate via ``require_permission`` *before* creating any Job — so a
    source whose creator lacks an active permission raises
    ``PermissionRequiredError`` and leaves no Job row (criterion 2). Otherwise a
    ``running`` ingest Job is created and the stages run in order, advancing
    ``job.stage``/``job.progress``; on success the Job is ``done`` with
    ``progress == 1.0`` (criterion 1).

    Any stage failure is caught and recorded on the Job
    (``status = error``, ``stage`` = the failing step, ``error`` = the message)
    and the Job is returned rather than re-raised, so the caller/worker does not
    crash (criterion 3). The dependencies default to the real implementations
    but are injectable so unit tests can run the sequence with fakes.
    """
    source = session.get(Source, source_id)
    if source is None:
        raise SourceNotFoundError(f"source {source_id} not found")

    # Re-check consent at processing time. Raises before any Job exists, so a
    # refused ingest leaves nothing in `done` (or anywhere).
    require_permission(session, source.creator_id)

    deps = IngestDeps(
        probe=probe_fn or probe,
        extract=extract_fn or extract_audio,
        transcriber=transcriber if transcriber is not None else _default_transcriber(),
    )

    job = Job(source_id=source.id, kind="ingest", status=JobStatus.running, progress=0.0)
    session.add(job)
    session.flush()  # assign the Job's primary key without ending the transaction

    storage_dir = get_settings().storage_dir
    try:
        run_stages(job, source, deps, storage_dir=storage_dir)
    except Exception as exc:  # noqa: BLE001 - any stage failure becomes Job state
        # Capture onto the Job (the failing `job.stage` is already set) instead
        # of propagating: one bad source must not take down the worker.
        job.status = JobStatus.error
        job.error = str(exc)
        return job

    job.status = JobStatus.done
    job.progress = 1.0
    return job


def _default_transcriber() -> Transcriber:
    """Construct the real `WhisperTranscriber` lazily.

    Deferred so importing this module (and running the unit tests, which always
    inject a mock) never imports faster-whisper.
    """
    from clipper.transcribe.whisper_local import WhisperTranscriber

    return WhisperTranscriber()
