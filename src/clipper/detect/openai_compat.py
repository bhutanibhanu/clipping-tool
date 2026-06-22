"""OpenAI-compatible `Detector` — the free local/dev sibling of `claude.py`.

This provider talks to any OpenAI-compatible ``/chat/completions`` endpoint —
**Ollama** locally (free, no key) or a keyed cloud endpoint (OpenRouter, Groq,
…) — using the already-present ``httpx`` (no new dependency). It is the *dev/test
convenience* path from ``docs/adr/0001-detection-provider-architecture.md``
(decision 7): it shares ``prompt.py`` (Core-4) and ``postprocess.py`` with the
canonical `ClaudeDetector`, so the two providers can never silently drift. The
local model is **not** the production path — production stays cloud-Claude on the
8 GB Air; a local-model eval only sketches quality and exercises the plumbing.

It mirrors `claude.py`'s shape: one request carries the whole transcript and
forces a single function call (``report_clips``) whose ``parameters`` is the
shared ``CANDIDATE_TOOL_SCHEMA``; we read the candidates out, validate each into
a `CandidateClip`, run the shared `postprocess`, and return the top
``max_clips``.

Robustness contract (matches `claude.py` and the T3B spec):
  * Empty ``base_url`` -> `DetectorConfigError` (a real misconfiguration). There
    is no missing-key path: Ollama needs no key, so a blank key is valid.
  * Transport error, non-2xx status, no parseable tool call / content JSON, or
    all-invalid items -> ``[]`` + a logged warning. The model (or a flaky local
    server) being sloppy is a quality problem, not an exception.

Parsing is deliberately Ollama-friendly: the primary path reads
``choices[0].message.tool_calls[0].function.arguments`` (a JSON *string*), and a
fallback extracts ``{"candidates": [...]}`` from ``message.content`` for local
models that emit the JSON as plain content instead of a tool call.

Testability: the HTTP layer is injectable. Tests pass a fake ``httpx.Client``
whose ``.post`` returns a canned, OpenAI-shaped response, so nothing here touches
the network or needs a key.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Protocol

import httpx
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
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

_TOOL_NAME = "report_clips"
_TOOL_DESCRIPTION = (
    "Report the clip-worthy moments you found in the transcript, ranked "
    "best-first, as structured candidates."
)
# Local models on CPU can be slow; a generous read timeout keeps a real Ollama
# run from spuriously failing while still bounding a hung server.
_TIMEOUT_SECONDS = 120.0


class _PostClient(Protocol):
    """The slice of ``httpx.Client`` this provider needs — just ``.post``.

    Declaring the seam as a Protocol lets tests inject a tiny fake (a single
    ``post`` method) without subclassing ``httpx.Client``.
    """

    def post(
        self,
        url: str,
        *,
        json: Any = ...,
        headers: Mapping[str, str] | None = ...,
    ) -> httpx.Response: ...


class OpenAICompatDetector:
    """`Detector` backed by an OpenAI-compatible ``/chat/completions`` endpoint.

    Pass ``client`` to inject a (possibly fake) object exposing ``.post`` —
    tests do exactly this. When ``None``, a real ``httpx.Client`` is created
    lazily on first use, so merely *constructing* an ``OpenAICompatDetector``
    never opens a connection. ``base_url``/``model``/``api_key`` come from
    ``Settings`` (Ollama defaults; no key required).
    """

    def __init__(
        self,
        client: _PostClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._client = client
        self._settings = settings or get_settings()

    def _get_client(self) -> _PostClient:
        """Return the injected client, or lazily build a real ``httpx.Client``."""
        if self._client is None:
            self._client = httpx.Client(timeout=_TIMEOUT_SECONDS)
        return self._client

    def _headers(self) -> dict[str, str]:
        """Build request headers, adding bearer auth only when a key is set.

        Ollama needs no auth, so an empty ``openai_api_key`` sends no
        ``Authorization`` header; a non-empty key (cloud endpoint) is forwarded.
        """
        headers = {"Content-Type": "application/json"}
        if self._settings.openai_api_key:
            headers["Authorization"] = f"Bearer {self._settings.openai_api_key}"
        return headers

    def detect(self, transcript: Transcript, *, max_clips: int = 5) -> list[CandidateClip]:
        base_url = self._settings.openai_base_url.rstrip("/")
        if not base_url:
            raise DetectorConfigError(
                "openai_base_url is empty; cannot run the OpenAI-compatible "
                "detector. Set CLIPPER_OPENAI_BASE_URL (e.g. "
                "http://localhost:11434/v1 for Ollama) or use a different provider."
            )

        client = self._get_client()
        source_duration = max((seg.end for seg in transcript.segments), default=0.0)

        payload: dict[str, Any] = {
            "model": self._settings.openai_model,
            "messages": [
                {"role": "system", "content": build_system_prompt(max_clips)},
                {"role": "user", "content": build_user_prompt(transcript)},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": _TOOL_NAME,
                        "description": _TOOL_DESCRIPTION,
                        "parameters": CANDIDATE_TOOL_SCHEMA,
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": _TOOL_NAME}},
            # Unlike claude-opus-4-8, OpenAI-compatible endpoints accept
            # `temperature`, so we always send it (0.0 default = deterministic).
            "temperature": self._settings.detector_temperature,
        }

        try:
            response = client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            logger.warning("OpenAI-compat detector: request failed: %s", exc)
            return []
        except (ValueError, json.JSONDecodeError) as exc:
            # Non-JSON body from a misbehaving endpoint.
            logger.warning("OpenAI-compat detector: response body was not JSON: %s", exc)
            return []

        raw = _extract_candidates(body)
        if not raw:
            return []

        candidates = _validate_candidates(raw)
        if not candidates:
            logger.warning("OpenAI-compat detector: no valid candidates after validation.")
            return []

        ranked = postprocess(candidates, list(transcript.segments), source_duration)
        return ranked[:max_clips]


def _first_message(body: object) -> dict[str, Any] | None:
    """Pull ``choices[0].message`` out of a parsed response, or ``None``.

    Tolerant of the many shapes a flaky local server can return (missing keys,
    wrong types, empty ``choices``); never raises.
    """
    if not isinstance(body, dict):
        logger.warning("OpenAI-compat detector: response body was not an object.")
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        logger.warning("OpenAI-compat detector: response had no choices.")
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        logger.warning("OpenAI-compat detector: first choice had no message object.")
        return None
    return message


def _candidates_from_tool_calls(message: dict[str, Any]) -> list[Any] | None:
    """Read candidates from ``message.tool_calls[0].function.arguments``.

    ``arguments`` is a JSON *string* (OpenAI function-calling); we ``json.loads``
    it and pull ``candidates``. Returns ``None`` (so the caller can try the
    content fallback) when there is no usable tool call; returns ``[]`` only when
    a tool call is present but carries no candidates list.
    """
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        return None
    first = tool_calls[0]
    function = first.get("function") if isinstance(first, dict) else None
    if not isinstance(function, dict):
        return None
    arguments = function.get("arguments")
    if not isinstance(arguments, str):
        return None
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError as exc:
        logger.warning("OpenAI-compat detector: tool_call arguments were not JSON: %s", exc)
        return []
    candidates = parsed.get("candidates") if isinstance(parsed, dict) else None
    if not isinstance(candidates, list):
        logger.warning("OpenAI-compat detector: tool_call arguments had no candidates list.")
        return []
    return candidates


def _candidates_from_content(message: dict[str, Any]) -> list[Any]:
    """Fallback: extract ``{"candidates": [...]}`` embedded in ``message.content``.

    Some local models ignore the tool definition and emit the JSON as plain
    content (optionally wrapped in prose or a ```` ```json ```` fence). We locate
    the outermost ``{...}`` span and parse it. Returns ``[]`` (never raises) when
    nothing parseable is found.
    """
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        return []
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        logger.warning("OpenAI-compat detector: message content had no JSON object.")
        return []
    try:
        parsed = json.loads(content[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("OpenAI-compat detector: message content was not parseable JSON: %s", exc)
        return []
    candidates = parsed.get("candidates") if isinstance(parsed, dict) else None
    if not isinstance(candidates, list):
        logger.warning("OpenAI-compat detector: message content had no candidates list.")
        return []
    return candidates


def _extract_candidates(body: object) -> list[Any]:
    """Pull the ``candidates`` list from a parsed chat-completions response.

    Primary path: the forced ``report_clips`` function call's JSON ``arguments``.
    Fallback: a ``{"candidates": [...]}`` object embedded in the message content
    (Ollama-friendly). Returns ``[]`` (and logs a warning) when neither yields a
    list — never raises.
    """
    message = _first_message(body)
    if message is None:
        return []

    from_tool = _candidates_from_tool_calls(message)
    if from_tool is not None:
        # A tool call was present (possibly empty/malformed -> []); trust it and
        # do not also try the content fallback.
        return from_tool

    return _candidates_from_content(message)


def _validate_candidates(raw: list[Any]) -> list[CandidateClip]:
    """Validate each raw item into a `CandidateClip`, skipping invalid ones.

    Mirrors `claude.py`: bad items (missing required fields, wrong types,
    out-of-range score, ``end <= 0``) are dropped with a warning rather than
    failing the whole batch — partial model sloppiness shouldn't lose the good
    candidates.
    """
    out: list[CandidateClip] = []
    for item in raw:
        if not isinstance(item, dict):
            logger.warning("OpenAI-compat detector: skipping non-object candidate %r.", item)
            continue
        try:
            out.append(CandidateClip.model_validate(item))
        except ValidationError as exc:
            logger.warning("OpenAI-compat detector: skipping invalid candidate: %s", exc)
    return out
