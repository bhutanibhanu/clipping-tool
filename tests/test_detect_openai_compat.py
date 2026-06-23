"""Unit tests for the OpenAI-compatible detection provider — NO network, NO key.

A fake stands in for ``httpx.Client``: its ``.post`` records the call and returns
a canned, OpenAI-shaped response (``choices[0].message`` carrying either
``tool_calls`` with a JSON-string ``arguments`` or plain ``content``). We assert
that ``OpenAICompatDetector.detect`` parses that into postprocessed
``CandidateClip``s, that the Ollama-friendly content fallback works, and that the
robustness paths (no tool call, malformed JSON, transport error) and the empty
``base_url`` config error behave per the T3B contract. The real network/Ollama
path is exercised only by humans (T6 de-risking).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from clipper.config import Settings
from clipper.detect import openai_compat
from clipper.detect.base import CandidateClip, Detector, DetectorConfigError
from clipper.detect.openai_compat import OpenAICompatDetector
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


# --- fake httpx plumbing -----------------------------------------------------


class FakeResponse:
    """Minimal ``httpx.Response`` stand-in: ``.json()`` + ``.raise_for_status()``."""

    def __init__(self, payload: Any, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=httpx.Request("POST", "http://test/chat/completions"),
                response=httpx.Response(self.status_code),
            )


class FakeClient:
    """Records ``.post`` calls and returns a canned response (or raises)."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: Any = None, headers: Any = None) -> Any:
        self.calls.append({"url": url, "json": json, "headers": headers})
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class FakeSequenceClient:
    """Returns queued responses in order; an `Exception` entry is raised instead.

    Mirrors `FakeClient` but pops one response per ``.post`` so a test can model a
    flaky endpoint (e.g. 503, then a good response). Recording ``.calls`` lets a
    test assert exactly how many requests the retry loop issued. Exhausting the
    queue is a test-construction error (``IndexError``).
    """

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, *, json: Any = None, headers: Any = None) -> Any:
        self.calls.append({"url": url, "json": json, "headers": headers})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _tool_call_response(candidates: list[dict[str, Any]]) -> FakeResponse:
    """An OpenAI-style response whose function `arguments` is a JSON string."""
    arguments = json.dumps({"candidates": candidates})
    return FakeResponse(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "report_clips", "arguments": arguments},
                            }
                        ],
                    }
                }
            ]
        }
    )


def _content_response(content: str) -> FakeResponse:
    """An OpenAI-style response with no tool_calls — JSON (or prose) in content."""
    return FakeResponse({"choices": [{"message": {"role": "assistant", "content": content}}]})


def _candidate_dicts() -> list[dict[str, Any]]:
    """Two distinct, non-overlapping, well-formed candidates."""
    return [
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


def _detector_with(
    response: Any, settings: Settings | None = None
) -> tuple[OpenAICompatDetector, FakeClient]:
    client = FakeClient(response)
    detector = OpenAICompatDetector(client=client, settings=settings or Settings())
    return detector, client


# --- tests -------------------------------------------------------------------


def test_openai_compat_detector_satisfies_the_protocol() -> None:
    assert isinstance(OpenAICompatDetector(client=FakeClient(_content_response(""))), Detector)


def test_detect_parses_tool_calls_into_ranked_candidates(transcript: Transcript) -> None:
    detector, _ = _detector_with(_tool_call_response(_candidate_dicts()))

    clips = detector.detect(transcript, max_clips=5)

    assert clips, "expected candidates from a well-formed tool_calls response"
    assert all(isinstance(c, CandidateClip) for c in clips)
    # Ranked by descending score.
    scores = [c.score for c in clips]
    assert scores == sorted(scores, reverse=True)
    # Postprocess snaps/clamps within source bounds and keeps 20-60s durations.
    for c in clips:
        assert 0.0 <= c.start < c.end <= SOURCE_DURATION
        assert 20.0 <= c.duration <= 60.0
    assert clips[0].score == 0.9


def test_detect_respects_max_clips(transcript: Transcript) -> None:
    detector, _ = _detector_with(_tool_call_response(_candidate_dicts()))

    clips = detector.detect(transcript, max_clips=1)

    assert len(clips) <= 1


def test_detect_issues_one_post_with_expected_request_shape(transcript: Transcript) -> None:
    detector, client = _detector_with(_tool_call_response(_candidate_dicts()))

    detector.detect(transcript, max_clips=5)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"] == "http://localhost:11434/v1/chat/completions"
    body = call["json"]
    assert body["model"] == Settings().openai_model
    # Two messages: system (Core-4) + user (transcript).
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    # JSON-schema structured-output shape, binding our shared candidate schema.
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "report_clips"
    assert body["response_format"]["json_schema"]["schema"]["required"] == ["candidates"]
    # OpenAI-compat endpoints accept temperature; it is always sent.
    assert body["temperature"] == Settings().detector_temperature


def test_detect_content_json_fallback(transcript: Transcript) -> None:
    # No tool_calls, but the message content carries the JSON object.
    content = "Here are the clips:\n" + json.dumps({"candidates": _candidate_dicts()})
    detector, _ = _detector_with(_content_response(content))

    clips = detector.detect(transcript, max_clips=5)

    assert len(clips) == 2
    assert clips[0].score == 0.9


def test_detect_content_json_fallback_with_code_fence(transcript: Transcript) -> None:
    # A fenced ```json block is still found by the outermost-brace extraction.
    inner = json.dumps({"candidates": _candidate_dicts()[:1]})
    content = f"```json\n{inner}\n```"
    detector, _ = _detector_with(_content_response(content))

    clips = detector.detect(transcript, max_clips=5)

    assert len(clips) == 1
    assert clips[0].title == "The interesting middle"


def test_no_tool_calls_and_no_parseable_content_returns_empty(transcript: Transcript) -> None:
    detector, _ = _detector_with(_content_response("Sorry, I found nothing useful."))

    assert detector.detect(transcript, max_clips=5) == []


def test_malformed_tool_call_arguments_returns_empty(transcript: Transcript) -> None:
    # `arguments` is present but not valid JSON -> [] and no raise.
    bad = FakeResponse(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": "report_clips", "arguments": "{not json"}}
                        ]
                    }
                }
            ]
        }
    )
    detector, _ = _detector_with(bad)

    assert detector.detect(transcript, max_clips=5) == []


def test_transport_error_returns_empty(
    transcript: Transcript, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A transport error is transient, so it is retried to exhaustion -> [].
    monkeypatch.setattr(openai_compat.time, "sleep", lambda _seconds: None)
    detector, client = _detector_with(httpx.ConnectError("connection refused"))

    assert detector.detect(transcript, max_clips=5) == []
    assert len(client.calls) == openai_compat._MAX_ATTEMPTS


def test_non_2xx_status_returns_empty(
    transcript: Transcript, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A non-retryable status (404) -> [] immediately, with no retry.
    monkeypatch.setattr(openai_compat.time, "sleep", lambda _seconds: None)
    detector, client = _detector_with(FakeResponse({}, status_code=404))

    assert detector.detect(transcript, max_clips=5) == []
    assert len(client.calls) == 1


def _sequence_detector(responses: list[Any]) -> tuple[OpenAICompatDetector, FakeSequenceClient]:
    client = FakeSequenceClient(responses)
    return OpenAICompatDetector(client=client, settings=Settings()), client


def test_retryable_status_then_success_retries_once(
    transcript: Transcript, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 503 (free-tier throttle) then a good response -> succeeds on the 2nd call.
    monkeypatch.setattr(openai_compat.time, "sleep", lambda _seconds: None)
    detector, client = _sequence_detector(
        [FakeResponse({}, status_code=503), _tool_call_response(_candidate_dicts())]
    )

    clips = detector.detect(transcript, max_clips=5)

    assert len(clips) == 2
    assert clips[0].score == 0.9
    assert len(client.calls) == 2  # retried exactly once


def test_all_retryable_statuses_exhaust_attempts(
    transcript: Transcript, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Persistent 503 -> [] after exactly _MAX_ATTEMPTS calls (retries capped).
    monkeypatch.setattr(openai_compat.time, "sleep", lambda _seconds: None)
    detector, client = _sequence_detector(
        [FakeResponse({}, status_code=503) for _ in range(openai_compat._MAX_ATTEMPTS + 2)]
    )

    assert detector.detect(transcript, max_clips=5) == []
    assert len(client.calls) == openai_compat._MAX_ATTEMPTS


def test_non_retryable_status_is_not_retried(
    transcript: Transcript, monkeypatch: pytest.MonkeyPatch
) -> None:
    # HTTP 400 is a client error: fail immediately even if a good response is queued.
    monkeypatch.setattr(openai_compat.time, "sleep", lambda _seconds: None)
    detector, client = _sequence_detector(
        [FakeResponse({}, status_code=400), _tool_call_response(_candidate_dicts())]
    )

    assert detector.detect(transcript, max_clips=5) == []
    assert len(client.calls) == 1  # no retry


def test_transport_error_then_success_retries(
    transcript: Transcript, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A one-off connect error is retried, then the good response succeeds.
    monkeypatch.setattr(openai_compat.time, "sleep", lambda _seconds: None)
    detector, client = _sequence_detector(
        [httpx.ConnectError("connection refused"), _tool_call_response(_candidate_dicts())]
    )

    clips = detector.detect(transcript, max_clips=5)

    assert len(clips) == 2
    assert len(client.calls) == 2


def test_all_items_invalid_returns_empty(transcript: Transcript) -> None:
    detector, _ = _detector_with(_tool_call_response([{"start": 1.0}]))

    assert detector.detect(transcript, max_clips=5) == []


def test_invalid_items_are_skipped_but_valid_ones_kept(transcript: Transcript) -> None:
    candidates: list[dict[str, Any]] = [
        {"start": 0.0},  # invalid: missing required fields
        {
            "start": 30.0,
            "end": 90.0,
            "score": 0.8,
            "reason": "Hook + payload.",
            "title": "Keeper",
        },
    ]
    detector, _ = _detector_with(_tool_call_response(candidates))

    clips = detector.detect(transcript, max_clips=5)

    assert len(clips) == 1
    assert clips[0].title == "Keeper"


def test_auth_header_present_only_when_key_set(transcript: Transcript) -> None:
    # No key (Ollama default): no Authorization header.
    detector, client = _detector_with(_tool_call_response(_candidate_dicts()))
    detector.detect(transcript, max_clips=5)
    assert "Authorization" not in client.calls[0]["headers"]

    # With a key (cloud endpoint): bearer auth is sent.
    keyed, keyed_client = _detector_with(
        _tool_call_response(_candidate_dicts()),
        settings=Settings(openai_api_key="sk-test-123"),
    )
    keyed.detect(transcript, max_clips=5)
    assert keyed_client.calls[0]["headers"]["Authorization"] == "Bearer sk-test-123"


def test_empty_base_url_raises_config_error(transcript: Transcript) -> None:
    detector, _ = _detector_with(
        _tool_call_response(_candidate_dicts()),
        settings=Settings(openai_base_url=""),
    )

    with pytest.raises(DetectorConfigError):
        detector.detect(transcript, max_clips=5)


def test_empty_choices_returns_empty(transcript: Transcript) -> None:
    detector, _ = _detector_with(FakeResponse({"choices": []}))

    assert detector.detect(transcript, max_clips=5) == []
