"""clipper command-line entry point (Phase 0: version + doctor).

`doctor` is the end-to-end smoke check — it touches config, the ffmpeg
wrapper, and reports readiness, so a fresh install can confirm the package
is wired together before any real pipeline exists.
"""

from __future__ import annotations

import os

import typer

from clipper import __version__
from clipper.config import get_settings
from clipper.media.ffmpeg import ffmpeg_available

app = typer.Typer(
    help="clipper — local-first AI clipping tool (Phase 0 skeleton).",
    no_args_is_help=True,
    add_completion=False,
)


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
