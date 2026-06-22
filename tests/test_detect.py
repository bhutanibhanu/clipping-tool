from __future__ import annotations

from clipper.detect.base import CandidateClip, Detector
from clipper.detect.mock import MockDetector
from clipper.transcribe.base import Transcript


def test_mock_detector_satisfies_the_protocol() -> None:
    assert isinstance(MockDetector(), Detector)


def test_mock_detector_returns_valid_candidates(transcript: Transcript) -> None:
    clips = MockDetector().detect(transcript, max_clips=2)
    assert 1 <= len(clips) <= 2
    for c in clips:
        assert isinstance(c, CandidateClip)
        assert c.end > c.start
        assert 0.0 <= c.score <= 1.0
        assert c.title


def test_mock_detector_handles_empty_transcript() -> None:
    assert MockDetector().detect(Transcript(segments=[])) == []
