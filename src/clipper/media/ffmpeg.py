"""Safe ffmpeg/ffprobe foundation.

Every invocation is built as an explicit argument list and run without a
shell — no string interpolation, so paths containing spaces (the project
dir is "clipping tool") and untrusted filenames are handled safely. The
stage-specific filters (cut, blurred-pad 9:16 reframe, burned captions)
build on top of this in Phase 3.
"""

from __future__ import annotations

import shutil
import subprocess


class FFmpegNotFoundError(RuntimeError):
    """Raised when ffmpeg/ffprobe is not available on PATH."""


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def ffmpeg_available() -> bool:
    """True only if both ffmpeg and ffprobe are on PATH."""
    return ffmpeg_path() is not None and ffprobe_path() is not None


def require_ffmpeg() -> None:
    if not ffmpeg_available():
        raise FFmpegNotFoundError(
            "ffmpeg/ffprobe not found on PATH. Install it with: brew install ffmpeg"
        )


def run(args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    """Run an ffmpeg/ffprobe command from an explicit arg list (never a shell string).

    Raises FFmpegNotFoundError if ffmpeg is missing and CalledProcessError on
    a non-zero exit (stderr is captured for diagnostics).
    """
    require_ffmpeg()
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
