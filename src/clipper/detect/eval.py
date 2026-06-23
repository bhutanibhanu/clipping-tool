"""Pure formatter for the detection eval report (`clipper detect --eval`).

This is the *build* side of the Phase-2 go/no-go gate (see
``docs/features/detection/eval.md``): it renders the top candidates as a single
human-scannable string the CLI prints, so the operator can score each against
the Core-4 rubric and decide PASS/revise. It is deliberately pure — input is
the candidates plus the transcript segments plus run metadata, output is a
``str`` — so it never touches the network or the DB and stays trivially
testable. The CLI owns I/O and persistence (and, on the eval path, persists
nothing).

The header tags every report with provider + model + ``PROMPT_VERSION`` + the
source id so a run pasted into the results log is attributable to an exact
prompt revision. The per-clip transcript excerpt is *derived locally* via
`excerpt_for` (the same helper persistence uses), never echoed by the model
(ADR-0001) — it is what was actually said in ``[start, end]``.
"""

from __future__ import annotations

from collections.abc import Sequence

from clipper.detect.base import CandidateClip
from clipper.detect.service import excerpt_for
from clipper.transcribe.base import Segment

# Excerpt cap (characters) so a long moment's text stays a scannable row rather
# than flooding the report. Truncated excerpts get an ellipsis appended.
_EXCERPT_MAX_CHARS = 200


def _mmss(seconds: float) -> str:
    """Render seconds as ``mm:ss`` (matches the CLI summary / prompt formatting)."""
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def _truncate(text: str, limit: int = _EXCERPT_MAX_CHARS) -> str:
    """Trim ``text`` to ``limit`` chars, appending an ellipsis when shortened."""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def format_eval_report(
    candidates: Sequence[CandidateClip],
    segments: Sequence[Segment],
    *,
    provider: str,
    model: str,
    prompt_version: str,
    source_id: int,
) -> str:
    """Render ranked ``candidates`` as a human-scannable eval report string.

    The first line is a header tagging the run with ``provider``, ``model``,
    ``prompt_version``, the ``source_id``, and the candidate count, so a report
    pasted into the results log is fully attributable. Each candidate then gets
    a fixed block showing: rank, ``mm:ss-mm:ss`` timecode + duration, ``score``,
    its Core-4 ``reason``, the ``title``, and the locally derived transcript
    excerpt (via `excerpt_for`, truncated to keep rows scannable).

    Pure: no I/O, no DB, no persistence. ``segments`` is the source transcript's
    segment list, used only to derive each excerpt.
    """
    header = (
        f"Eval report — provider={provider} model={model} "
        f"prompt_version={prompt_version} source={source_id} "
        f"candidates={len(candidates)}"
    )
    lines: list[str] = [header]

    if not candidates:
        lines.append("  (no candidates)")
        return "\n".join(lines)

    for rank, cand in enumerate(candidates, start=1):
        score_str = f"{cand.score:.2f}"
        timecode = f"{_mmss(cand.start)}-{_mmss(cand.end)}"
        duration = f"{cand.duration:.1f}s"
        excerpt = _truncate(excerpt_for(segments, cand.start, cand.end)) or "(no transcript text)"
        lines.append("")
        lines.append(f"#{rank}  {timecode} ({duration})  score={score_str}")
        lines.append(f"    title  : {cand.title}")
        lines.append(f"    reason : {cand.reason}")
        lines.append(f"    excerpt: {excerpt}")

    return "\n".join(lines)
