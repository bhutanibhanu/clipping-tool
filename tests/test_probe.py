from __future__ import annotations

from pathlib import Path

import pytest

from clipper.media import ffmpeg
from clipper.media.audio import extract_audio
from clipper.media.probe import MediaInfo, _parse_probe, probe

# A realistic captured ffprobe `-print_format json -show_format -show_streams`
# payload: a video stream (1280x720), an audio stream, and format.duration.
_PROBE_JSON = """
{
  "streams": [
    {
      "index": 0,
      "codec_name": "h264",
      "codec_type": "video",
      "width": 1280,
      "height": 720,
      "r_frame_rate": "30/1"
    },
    {
      "index": 1,
      "codec_name": "aac",
      "codec_type": "audio",
      "sample_rate": "48000",
      "channels": 2
    }
  ],
  "format": {
    "filename": "input.mp4",
    "nb_streams": 2,
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "duration": "63.500000",
    "size": "1048576"
  }
}
"""


def test_parse_probe_maps_fields() -> None:
    info = _parse_probe(_PROBE_JSON)
    assert info == MediaInfo(duration=63.5, width=1280, height=720)
    assert isinstance(info.duration, float)


def test_parse_probe_picks_first_video_stream_for_resolution() -> None:
    # Audio stream listed first must not be mistaken for the video stream.
    payload = """
    {
      "streams": [
        {"codec_type": "audio", "channels": 1},
        {"codec_type": "video", "width": 320, "height": 240}
      ],
      "format": {"duration": "10.0"}
    }
    """
    assert _parse_probe(payload) == MediaInfo(duration=10.0, width=320, height=240)


def test_probe_raises_when_ffmpeg_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    with pytest.raises(ffmpeg.FFmpegNotFoundError):
        probe(tmp_path / "missing.mp4")


def test_extract_audio_raises_when_ffmpeg_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda _name: None)
    with pytest.raises(ffmpeg.FFmpegNotFoundError):
        extract_audio(tmp_path / "in.mp4", tmp_path / "out.wav")


@pytest.mark.integration
@pytest.mark.skipif(not ffmpeg.ffmpeg_available(), reason="ffmpeg not available")
def test_probe_reads_synthetic_clip(synthetic_clip: Path) -> None:
    info = probe(synthetic_clip)
    assert info.width == 320
    assert info.height == 240
    assert info.duration == pytest.approx(10.0, abs=0.5)


@pytest.mark.integration
@pytest.mark.skipif(not ffmpeg.ffmpeg_available(), reason="ffmpeg not available")
def test_extract_audio_produces_16k_mono_wav(synthetic_clip: Path, tmp_path: Path) -> None:
    dst = tmp_path / "audio" / "out.wav"
    result = extract_audio(synthetic_clip, dst)

    assert result == dst
    assert dst.exists() and dst.stat().st_size > 0

    info = _audio_stream(dst)
    assert int(info["channels"]) == 1
    assert int(info["sample_rate"]) == 16000


def _audio_stream(path: Path) -> dict[str, object]:
    """ffprobe the first audio stream of `path` (integration helper)."""
    import json

    result = ffmpeg.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-select_streams",
            "a:0",
            "-show_streams",
            str(path),
        ]
    )
    streams = json.loads(result.stdout)["streams"]
    return streams[0]
