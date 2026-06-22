from __future__ import annotations

import pytest

from clipper.transcribe.base import Segment, Transcript


@pytest.fixture
def transcript() -> Transcript:
    return Transcript(
        segments=[
            Segment(0.0, 6.0, "Welcome to the show, today we have a great guest."),
            Segment(6.0, 30.0, "Here is a genuinely interesting story about the early days."),
            Segment(30.0, 75.0, "And then came the surprising twist that changed everything."),
        ],
        language="en",
    )
