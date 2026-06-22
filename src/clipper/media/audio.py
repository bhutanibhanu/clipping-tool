"""Extract a transcription-ready audio track from a media file.

faster-whisper expects 16 kHz mono PCM; this downmixes and resamples to that
via the safe ffmpeg wrapper (`clipper.media.ffmpeg`) using an explicit argument
list and no shell, so spaces and untrusted filenames are handled safely.
"""

from __future__ import annotations

from pathlib import Path

from clipper.media import ffmpeg


def extract_audio(src: Path, dst: Path) -> Path:
    """Write a 16 kHz mono WAV of `src` to `dst` and return `dst`.

    Creates `dst`'s parent directory if needed. Raises `FFmpegNotFoundError`
    if ffmpeg/ffprobe is absent.
    """
    ffmpeg.require_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(dst),
        ]
    )
    return dst
