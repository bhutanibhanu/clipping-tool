"""clipper command-line entry point.

`doctor` is the end-to-end smoke check — it touches config, the ffmpeg
wrapper, and reports readiness, so a fresh install can confirm the package
is wired together before any real pipeline exists. The `creator` and
`permission` sub-apps seed the consent records the pipeline gate depends on.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from clipper import __version__
from clipper.catalog import SourceFileNotFoundError, create_creator, register_source
from clipper.config import get_settings
from clipper.db.models import Clip, JobStatus
from clipper.db.session import session_scope
from clipper.detect.base import DetectorConfigError
from clipper.detect.service import (
    PROVIDER_CLAUDE,
    PROVIDER_MOCK,
    TranscriptMissingError,
    detect_for_source,
    make_detector,
)
from clipper.detect.service import (
    SourceNotFoundError as DetectSourceNotFoundError,
)
from clipper.media.ffmpeg import ffmpeg_available
from clipper.permissions.service import (
    AuthorizationFileNotFoundError,
    CreatorNotFoundError,
    PermissionRequiredError,
    grant_permission,
)
from clipper.pipeline.jobs import SourceNotFoundError, run_ingest
from clipper.transcribe.whisper_local import TranscriberUnavailableError

app = typer.Typer(
    help="clipper — local-first AI clipping tool.",
    no_args_is_help=True,
    add_completion=False,
)

creator_app = typer.Typer(help="Manage creators (the authorized content owners).")
permission_app = typer.Typer(help="Manage permission records (proof of consent).")
source_app = typer.Typer(help="Register source videos (gated on an active permission).")
app.add_typer(creator_app, name="creator")
app.add_typer(permission_app, name="permission")
app.add_typer(source_app, name="source")


@app.command()
def version() -> None:
    """Print the clipper version."""
    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Report environment and configuration readiness."""
    s = get_settings()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    typer.echo(f"clipper {__version__}")
    typer.echo(f"  storage dir        : {s.storage_dir}")
    typer.echo(f"  db url             : {s.db_url}")
    typer.echo(f"  whisper model      : {s.whisper_model} ({s.whisper_compute_type})")
    typer.echo(f"  worker concurrency : {s.worker_concurrency}")
    typer.echo(f"  detector model     : {s.detector_model}")
    typer.echo(f"  ANTHROPIC_API_KEY  : {'set' if has_key else 'MISSING (needed for Phase 2)'}")
    typer.echo(
        f"  ffmpeg available   : {'yes' if ffmpeg_available() else 'no  (brew install ffmpeg)'}"
    )


@creator_app.command("add")
def creator_add(
    name: str = typer.Option(..., "--name", help="Display name of the creator."),
) -> None:
    """Create a creator and print its id (initializes the DB if absent)."""
    with session_scope() as session:
        creator = create_creator(session, name=name)
        session.flush()
        creator_id = creator.id
    typer.echo(f"Created creator {creator_id}: {name}")


@permission_app.command("grant")
def permission_grant(
    creator: int = typer.Option(..., "--creator", help="Creator id to grant permission to."),
    scope: str = typer.Option(..., "--scope", help="Scope of the authorization (free text)."),
    auth_file: Path = typer.Option(
        ...,
        "--auth-file",
        help="Path to the authorization file on disk (recorded, not copied).",
    ),
) -> None:
    """Grant an active permission for a creator, recording the auth file path."""
    try:
        with session_scope() as session:
            record = grant_permission(session, creator_id=creator, scope=scope, auth_file=auth_file)
            session.flush()
            record_id = record.id
            recorded_path = record.authorization_file_path
    except (CreatorNotFoundError, AuthorizationFileNotFoundError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Granted permission {record_id} (scope={scope}) for creator {creator}")
    typer.echo(f"  authorization file: {recorded_path}")


@source_app.command("add")
def source_add(
    file: Path = typer.Option(..., "--file", help="Path to the local video file to register."),
    creator: int = typer.Option(..., "--creator", help="Creator id the video belongs to."),
) -> None:
    """Register a video as a Source (refused unless the creator has consent on file)."""
    try:
        with session_scope() as session:
            source = register_source(session, creator_id=creator, file_path=file)
            session.flush()
            source_id = source.id
            recorded_path = source.file_path
    except SourceFileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except PermissionRequiredError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Created source {source_id} for creator {creator}")
    typer.echo(f"  file: {recorded_path}")


@app.command()
def ingest(
    source_id: int = typer.Argument(..., help="Id of the registered source to ingest."),
) -> None:
    """Run the ingest pipeline for a source: probe -> audio -> transcribe -> persist.

    Synchronous and single-worker. Refuses (exit 1) if the source is unknown or
    its creator lacks an active permission; if a stage fails the Job is recorded
    as ``error`` and the failing stage is printed (exit 1). On success prints the
    source's duration and transcript path.
    """
    try:
        with session_scope() as session:
            job = run_ingest(session, source_id)
            # Read everything we report INSIDE the session, before it closes.
            status = job.status
            stage = job.stage
            error = job.error
            duration = job.source.duration_seconds
            transcript_path = job.source.transcript_path
    except (PermissionRequiredError, SourceNotFoundError, TranscriberUnavailableError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if status is JobStatus.error:
        typer.echo(f"Error: ingest failed at stage '{stage}': {error}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Ingested source {source_id} (duration={duration}s)")
    typer.echo(f"  transcript: {transcript_path}")


def _mmss(seconds: float) -> str:
    """Render seconds as ``mm:ss`` for the detect summary."""
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


@app.command()
def detect(
    source_id: int = typer.Argument(..., help="Id of the ingested source to detect clips in."),
    provider: str = typer.Option(
        PROVIDER_CLAUDE,
        "--provider",
        help="Detection provider: claude, openai-compat, or mock.",
    ),
    mock: bool = typer.Option(
        False, "--mock", help="Shortcut for --provider mock (offline, no API key)."
    ),
    max_clips: int | None = typer.Option(
        None,
        "--max-clips",
        help="Max candidate clips to surface (default: Settings.detector_max_clips).",
    ),
) -> None:
    """Detect clip-worthy moments in a source and persist them as pending clips.

    Loads the source's transcript, runs the selected detector (Claude by
    default; ``--mock`` / ``--provider`` switch it), and writes one pending
    ``Clip`` row per ranked candidate with a locally derived transcript excerpt.
    Refuses (exit 1) if the source is unknown or has no transcript, or if the
    detector is misconfigured (e.g. ``ANTHROPIC_API_KEY`` unset).
    """
    selected = PROVIDER_MOCK if mock else provider
    try:
        detector = make_detector(selected)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        with session_scope() as session:
            clips = detect_for_source(session, source_id, detector=detector, max_clips=max_clips)
            # Read everything we report INSIDE the session, before it closes.
            summary = [
                (c.start_seconds, c.end_seconds, c.score, c.title)
                for c in clips
                if isinstance(c, Clip)
            ]
    except (DetectSourceNotFoundError, TranscriptMissingError, DetectorConfigError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Detected {len(summary)} candidate clips for source {source_id} (provider={selected}):"
    )
    for start, end, score, title in summary:
        score_str = f"{score:.2f}" if score is not None else "n/a"
        typer.echo(f"  {_mmss(start)}-{_mmss(end)}  score={score_str}  {title}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
