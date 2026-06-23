"""Claude-backed `Detector` — the canonical, production detection provider.

One `messages.create` call carries the whole transcript and forces a single
tool call (`report_clips`) whose ``input_schema`` is the shared
``CANDIDATE_TOOL_SCHEMA``. We read the candidates out of that tool call, validate
each into a `CandidateClip`, run the shared `postprocess` (snap/clamp/drop/dedup
/rank), and return the top ``max_clips``. See
``docs/adr/0001-detection-provider-architecture.md`` (decisions 1, 2, 4).

Robustness contract (matches the T3 spec):
  * Missing ``ANTHROPIC_API_KEY`` -> `DetectorConfigError` (never a raw SDK error).
  * No tool-use block, malformed input, or all-invalid items -> ``[]`` + a logged
    warning. The model being sloppy is a quality problem, not an exception.

Testability: the client is injectable. Tests pass a fake whose ``.messages.create``
returns a canned SDK-shaped response, so nothing here touches the network or
needs a key.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from clipper.config import Settings, get_settings
from clipper.detect.base import CandidateClip, DetectorConfigError
from clipper.detect.postprocess import postprocess
from clipper.detect.prompt import (
    CANDIDATE_TOOL_SCHEMA,
    build_system_prompt,
    build_user_prompt,
)
from clipper.transcribe.base import Transcript

if TYPE_CHECKING:
    from anthropic import Anthropic

logger = logging.getLogger(__name__)

_TOOL_NAME = "report_clips"
_TOOL_DESCRIPTION = (
    "Report the clip-worthy moments you found in the transcript, ranked "
    "best-first, as structured candidates."
)
# Generous enough for ~2x max_clips candidates with copy; far under any model cap.
_MAX_TOKENS = 4096


class ClaudeDetector:
    """`Detector` implementation backed by the Anthropic Messages API.

    Pass ``client`` to inject a (possibly fake) Anthropic client; when ``None``
    the real ``anthropic.Anthropic()`` is constructed lazily on first use, so
    merely *constructing* a `ClaudeDetector` never requires a key or network.
    """

    def __init__(self, client: Anthropic | None = None, settings: Settings | None = None) -> None:
        self._client = client
        self._settings = settings or get_settings()

    def _get_client(self) -> Anthropic:
        """Return the injected client, or lazily build a real one.

        A real client is only built when no client was injected; we check for the
        API key first and raise a clear `DetectorConfigError` rather than letting
        the SDK surface its own error at call time.
        """
        if self._client is not None:
            return self._client
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise DetectorConfigError(
                "ANTHROPIC_API_KEY is not set; cannot run the Claude detector. "
                "Set it in the environment or a .env file, or use a different "
                "detection provider."
            )
        import anthropic

        self._client = anthropic.Anthropic()
        return self._client

    def detect(self, transcript: Transcript, *, max_clips: int = 5) -> list[CandidateClip]:
        client = self._get_client()
        source_duration = max((seg.end for seg in transcript.segments), default=0.0)

        create_kwargs: dict[str, Any] = {
            "model": self._settings.detector_model,
            "max_tokens": _MAX_TOKENS,
            "system": build_system_prompt(max_clips),
            "messages": [{"role": "user", "content": build_user_prompt(transcript)}],
            "tools": [
                {
                    "name": _TOOL_NAME,
                    "description": _TOOL_DESCRIPTION,
                    "input_schema": CANDIDATE_TOOL_SCHEMA,
                }
            ],
            "tool_choice": {"type": "tool", "name": _TOOL_NAME},
        }
        # Only forward temperature when explicitly non-zero: claude-opus-4-7/4.8
        # (and Fable) reject the param with a 400, and the 0.0 default is exactly
        # the deterministic mode the ADR wants — so omitting it is both correct
        # for those models and faithful to ADR-0001 §3.
        if self._settings.detector_temperature > 0:
            create_kwargs["temperature"] = self._settings.detector_temperature

        response = client.messages.create(**create_kwargs)

        raw = _extract_candidates(response)
        if not raw:
            return []

        candidates = _validate_candidates(raw)
        if not candidates:
            logger.warning("Claude detector: no valid candidates after validation.")
            return []

        ranked = postprocess(candidates, list(transcript.segments), source_duration)
        return ranked[:max_clips]


def _extract_candidates(response: object) -> list[Any]:
    """Pull the ``candidates`` list out of the forced ``report_clips`` tool call.

    Returns ``[]`` (and logs a warning) if there is no matching ``tool_use``
    block or its input doesn't carry a candidates list — never raises.
    """
    content = getattr(response, "content", None)
    if not isinstance(content, list):
        logger.warning("Claude detector: response had no content blocks.")
        return []

    for block in content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if getattr(block, "name", None) != _TOOL_NAME:
            continue
        tool_input = getattr(block, "input", None)
        if not isinstance(tool_input, dict):
            logger.warning("Claude detector: tool_use input was not a dict.")
            return []
        candidates = tool_input.get("candidates")
        if not isinstance(candidates, list):
            logger.warning("Claude detector: tool_use input had no candidates list.")
            return []
        return candidates

    logger.warning("Claude detector: response carried no report_clips tool_use block.")
    return []


def _validate_candidates(raw: list[Any]) -> list[CandidateClip]:
    """Validate each raw item into a `CandidateClip`, skipping invalid ones.

    Individual bad items (missing required fields, wrong types, out-of-range
    score, ``end <= 0``) are dropped with a warning rather than failing the whole
    batch — partial model sloppiness shouldn't lose the good candidates.
    """
    out: list[CandidateClip] = []
    for item in raw:
        if not isinstance(item, dict):
            logger.warning("Claude detector: skipping non-object candidate %r.", item)
            continue
        try:
            out.append(CandidateClip.model_validate(item))
        except ValidationError as exc:
            logger.warning("Claude detector: skipping invalid candidate: %s", exc)
    return out
