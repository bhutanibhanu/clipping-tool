"""Unit tests for the Claude detection provider — NO network, NO API key.

A fake client stands in for ``anthropic.Anthropic``: its ``.messages.create``
returns a canned, SDK-shaped response (a ``content`` list whose one block mimics
a ``tool_use`` block with ``type``/``name``/``input``). We assert that
``ClaudeDetector.detect`` parses that into postprocessed ``CandidateClip``s, and
that the robustness paths (unset key, no tool_use, malformed input) behave per
the T3 contract. The real network/key path is exercised only by humans (T6).
"""

from __future__ import annotations

import types
from typing import Any

import pytest

from clipper.config import Settings
from clipper.detect.base import CandidateClip, Detector, DetectorConfigError
from clipper.detect.claude import ClaudeDetector
from clipper.transcribe.base import Segment, Transcript

# A contiguous ~5-minute transcript so candidates have room to snap/clamp/dedup.
SEGMENTS = [
    Segment(0.0, 30.0, "Intro and the hook that grabs you."),
    Segment(30.0, 90.0, "The genuinely interesting middle story."),
    Segment(90.0, 150.0, "A surprising twist with a real payload."),
    Segment(150.0, 220.0, "A second distinct moment later on."),
    Segment(220.0, 300.0, "Closing thoughts and a final opinion."),
]
SOURCE_DURATION = 300.0


@pytest.fixture
def transcript() -> Transcript:
    return Transcript(segments=list(SEGMENTS), language="en")


# --- fake SDK plumbing -------------------------------------------------------


def _tool_use_block(name: str, tool_input: dict[str, Any]) -> types.SimpleNamespace:
    """A stand-in for an SDK ToolUseBlock (`type`/`name`/`input` attributes)."""
    return types.SimpleNamespace(type="tool_use", name=name, input=tool_input)


def _text_block(text: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(type="text", text=text)


def _response(content: list[Any]) -> types.SimpleNamespace:
    return types.SimpleNamespace(content=content)


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._response


class FakeClient:
    """Minimal `anthropic.Anthropic` stand-in: just ``.messages.create``."""

    def __init__(self, response: Any) -> None:
        self.messages = FakeMessages(response)


def _candidate_payload() -> dict[str, Any]:
    """A well-formed tool input with two distinct, non-overlapping candidates."""
    return {
        "candidates": [
            {
                "start": 30.0,
                "end": 90.0,
                "score": 0.9,
                "reason": "Hook + payload + length-fit.",
                "title": "The interesting middle",
                "description": "A great story.",
                "hashtags": ["#story"],
            },
            {
                "start": 150.0,
                "end": 220.0,
                "score": 0.6,
                "reason": "Self-contained second moment.",
                "title": "Later moment",
                "description": "",
                "hashtags": [],
            },
        ]
    }


def _detector_with(response: Any) -> tuple[ClaudeDetector, FakeClient]:
    client = FakeClient(response)
    detector = ClaudeDetector(client=client, settings=Settings())
    return detector, client


# --- tests -------------------------------------------------------------------


def test_claude_detector_satisfies_the_protocol() -> None:
    assert isinstance(ClaudeDetector(client=FakeClient(_response([]))), Detector)


def test_detect_parses_tool_use_into_ranked_candidates(transcript: Transcript) -> None:
    response = _response([_tool_use_block("report_clips", _candidate_payload())])
    detector, _ = _detector_with(response)

    clips = detector.detect(transcript, max_clips=5)

    assert clips, "expected candidates from a well-formed tool_use response"
    assert all(isinstance(c, CandidateClip) for c in clips)
    # Ranked by descending score.
    scores = [c.score for c in clips]
    assert scores == sorted(scores, reverse=True)
    # Postprocess snaps/clamps within source bounds and keeps 20-60s durations.
    for c in clips:
        assert 0.0 <= c.start < c.end <= SOURCE_DURATION
        assert 20.0 <= c.duration <= 60.0
    # The top candidate is the higher-scored one.
    assert clips[0].score == 0.9


def test_detect_respects_max_clips(transcript: Transcript) -> None:
    response = _response([_tool_use_block("report_clips", _candidate_payload())])
    detector, _ = _detector_with(response)

    clips = detector.detect(transcript, max_clips=1)

    assert len(clips) <= 1


def test_detect_issues_exactly_one_create_call(transcript: Transcript) -> None:
    response = _response([_tool_use_block("report_clips", _candidate_payload())])
    detector, client = _detector_with(response)

    detector.detect(transcript, max_clips=5)

    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    # The single request forces our one tool and targets the configured model.
    assert call["model"] == Settings().detector_model
    assert call["tool_choice"] == {"type": "tool", "name": "report_clips"}
    assert [t["name"] for t in call["tools"]] == ["report_clips"]
    assert call["tools"][0]["input_schema"]["required"] == ["candidates"]


def test_detect_omits_temperature_at_zero_default(transcript: Transcript) -> None:
    # claude-opus-4-8 rejects `temperature`; the 0.0 default must not be sent.
    response = _response([_tool_use_block("report_clips", _candidate_payload())])
    detector, client = _detector_with(response)

    detector.detect(transcript, max_clips=5)

    assert "temperature" not in client.messages.calls[0]


def test_detect_forwards_nonzero_temperature(transcript: Transcript) -> None:
    response = _response([_tool_use_block("report_clips", _candidate_payload())])
    client = FakeClient(response)
    detector = ClaudeDetector(client=client, settings=Settings(detector_temperature=0.4))

    detector.detect(transcript, max_clips=5)

    assert client.messages.calls[0]["temperature"] == 0.4


def test_unset_api_key_raises_config_error(
    transcript: Transcript, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No injected client + no key -> clear DetectorConfigError, not a raw SDK error.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    detector = ClaudeDetector(settings=Settings())

    with pytest.raises(DetectorConfigError):
        detector.detect(transcript, max_clips=5)


def test_no_tool_use_block_returns_empty(transcript: Transcript) -> None:
    response = _response([_text_block("I could not find any good clips.")])
    detector, _ = _detector_with(response)

    assert detector.detect(transcript, max_clips=5) == []


def test_wrong_tool_name_returns_empty(transcript: Transcript) -> None:
    response = _response([_tool_use_block("some_other_tool", _candidate_payload())])
    detector, _ = _detector_with(response)

    assert detector.detect(transcript, max_clips=5) == []


def test_malformed_input_not_a_dict_returns_empty(transcript: Transcript) -> None:
    response = _response(
        [types.SimpleNamespace(type="tool_use", name="report_clips", input="not-a-dict")]
    )
    detector, _ = _detector_with(response)

    # Returns [] and does NOT raise.
    assert detector.detect(transcript, max_clips=5) == []


def test_input_without_candidates_list_returns_empty(transcript: Transcript) -> None:
    response = _response([_tool_use_block("report_clips", {"clips": []})])
    detector, _ = _detector_with(response)

    assert detector.detect(transcript, max_clips=5) == []


def test_all_items_invalid_returns_empty(transcript: Transcript) -> None:
    # Missing required fields (only `start`) -> each item fails validation.
    response = _response(
        [_tool_use_block("report_clips", {"candidates": [{"start": 1.0}, "garbage"]})]
    )
    detector, _ = _detector_with(response)

    assert detector.detect(transcript, max_clips=5) == []


def test_invalid_items_are_skipped_but_valid_ones_kept(transcript: Transcript) -> None:
    payload = {
        "candidates": [
            {"start": 0.0},  # invalid: missing required fields
            {
                "start": 30.0,
                "end": 90.0,
                "score": 0.8,
                "reason": "Hook + payload.",
                "title": "Keeper",
            },
        ]
    }
    response = _response([_tool_use_block("report_clips", payload)])
    detector, _ = _detector_with(response)

    clips = detector.detect(transcript, max_clips=5)

    assert len(clips) == 1
    assert clips[0].title == "Keeper"


def test_empty_content_returns_empty(transcript: Transcript) -> None:
    detector, _ = _detector_with(_response([]))

    assert detector.detect(transcript, max_clips=5) == []
