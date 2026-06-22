"""Probe a media file's duration and resolution via ffprobe.

Built on the safe ffmpeg wrapper (`clipper.media.ffmpeg`): ffprobe is invoked
with an explicit argument list and no shell, so spaces and untrusted filenames
are handled safely. The JSON→result mapping is factored into a pure function
(`_parse_probe`) so it is unit-testable without ffmpeg installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from clipper.media import ffmpeg


@dataclass(frozen=True)
class MediaInfo:
    """Container/stream facts a probe needs: duration plus video resolution."""

    duration: float
    width: int
    height: int


def _parse_probe(payload: str) -> MediaInfo:
    """Map ffprobe's `-print_format json` output to a `MediaInfo`.

    Duration comes from `format.duration`; width/height from the first video
    stream. Pure (no ffmpeg) so it can be unit-tested against captured JSON.
    """
    data = json.loads(payload)
    duration = float(data["format"]["duration"])
    video = next(
        stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"
    )
    return MediaInfo(duration=duration, width=int(video["width"]), height=int(video["height"]))


def probe(path: Path) -> MediaInfo:
    """Probe `path` with ffprobe and return its duration and resolution.

    Raises `FFmpegNotFoundError` if ffmpeg/ffprobe is absent.
    """
    ffmpeg.require_ffmpeg()
    result = ffmpeg.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    return _parse_probe(result.stdout)
