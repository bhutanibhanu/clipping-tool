"""Provider-agnostic detection prompt + candidate schema.

This module is the **product's core bet** made legible: it owns the instructions
that tell an LLM how to find clip-worthy moments, plus the structured-output
schema both providers bind to. It is deliberately provider-neutral — the Claude
provider (`claude.py`) uses ``CANDIDATE_TOOL_SCHEMA`` as a tool ``input_schema``
and the OpenAI-compatible provider (T3B) uses the same dict as a function
``parameters`` block. Keeping one prompt + one schema here means a prompt change
is attributable to *this file* (versioned by ``PROMPT_VERSION``), and the two
providers can never silently drift apart. See
``docs/adr/0001-detection-provider-architecture.md`` (decision 2).

Nothing here touches the network, the DB, or `Settings`; it is pure text/data so
it stays trivially testable and importable from either provider.
"""

from __future__ import annotations

from clipper.transcribe.base import Transcript

# Bump this whenever the prompt or schema changes in a way that could move
# detection quality — the eval harness (T5) tags every run with it so the
# go/no-go log stays attributable to an exact prompt revision.
PROMPT_VERSION = "detect-v1"

# JSON Schema for the structured output, shared verbatim by both providers.
# Reusable as a Claude tool `input_schema` AND as OpenAI function `parameters`.
# `start`/`end`/`score`/`reason`/`title` are required; `description`/`hashtags`
# are optional (they default on `CandidateClip`). We intentionally do NOT set
# `additionalProperties: false` here: this dict feeds both Anthropic tool-use and
# OpenAI function-calling, and the strict-mode rules differ between them — the
# providers add provider-specific strictness if they want it. Postprocess +
# per-item validation (in the provider) are the real guardrails.
CANDIDATE_TOOL_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "description": "Clip-worthy moments, ranked best-first.",
            "items": {
                "type": "object",
                "properties": {
                    "start": {
                        "type": "number",
                        "description": (
                            "Clip start, in SECONDS from the beginning of the "
                            "source (a float matching the transcript timestamps)."
                        ),
                    },
                    "end": {
                        "type": "number",
                        "description": (
                            "Clip end, in SECONDS from the beginning of the "
                            "source. Must be greater than start; aim for a "
                            "20-60 second moment."
                        ),
                    },
                    "score": {
                        "type": "number",
                        "description": (
                            "Honest confidence, 0.0-1.0, that this clip is "
                            "postable as-is to short-form vertical video."
                        ),
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "Which of the Core-4 criteria (hook, self-contained, "
                            "payload, length-fit) this moment satisfies, and why."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "A punchy, scroll-stopping title/hook for the clip.",
                    },
                    "description": {
                        "type": "string",
                        "description": "A short caption/description for the post.",
                    },
                    "hashtags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A few relevant hashtags (with or without the leading #).",
                    },
                },
                "required": ["start", "end", "score", "reason", "title"],
            },
        }
    },
    "required": ["candidates"],
}


def _format_timestamp(seconds: float) -> str:
    """Render seconds as ``mm:ss`` for human-readable transcript lines."""
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def format_transcript(transcript: Transcript) -> str:
    """Render the transcript as timestamped lines the model can cut against.

    Each segment becomes one line ``[mm:ss-mm:ss] (start_s-end_s) text`` — the
    human-readable ``mm:ss`` makes the prompt scannable, while the explicit
    ``start_s``/``end_s`` floats are what we ask the model to copy into
    ``start``/``end`` (it must return SECONDS, not timecodes). Both are shown so
    the model never has to convert ``mm:ss`` back to seconds and get it wrong.
    """
    lines: list[str] = []
    for seg in transcript.segments:
        stamp = f"[{_format_timestamp(seg.start)}-{_format_timestamp(seg.end)}]"
        secs = f"({seg.start:.1f}-{seg.end:.1f}s)"
        lines.append(f"{stamp} {secs} {seg.text.strip()}")
    return "\n".join(lines)


def build_system_prompt(max_clips: int) -> str:
    """Build the system/instruction text for a detection request.

    The shape of this prompt is load-bearing — comments explain *why*:

    * **Core-4 rubric up front.** Hook / self-contained / payload / length-fit is
      the product's definition of "good clip"; stating it as explicit, gradeable
      criteria (rather than "find good moments") is what the go/no-go eval scores
      against, so the model and the human judge share one bar.
    * **Times in SECONDS as floats.** Postprocess snaps to segment boundaries, but
      it can only do that if the model returns real numbers on the transcript's
      scale — so we are emphatic about seconds, not ``mm:ss``.
    * **~2x candidates, ranked best-first.** Postprocess dedups overlaps and trims
      to ``max_clips``; over-requesting means ``max_clips`` *distinct* clips
      usually survive. Ranking best-first gives the stable-sort a sensible tie
      order.
    * **Honest score.** The score drives dedup tiebreaks and the eval's ranking,
      so we ask for calibrated confidence, not enthusiasm.
    * **reason states which criteria hit.** This is both a quality forcing-function
      (the model must justify the pick) and what the human reads in the eval.
    """
    target = max_clips * 2
    return (
        "You are an expert short-form video editor. You are given the full "
        "timestamped transcript of one long-form video. Your job is to find the "
        "moments that would make the best standalone 9:16 short-form clips "
        "(think Reels / Shorts / TikTok).\n"
        "\n"
        "Judge every candidate against the Core-4 rubric — the best clips satisfy "
        "all four:\n"
        "  1. HOOK — it grabs attention in the first ~2 seconds.\n"
        "  2. SELF-CONTAINED — it lands on its own, without needing the "
        "surrounding video for context.\n"
        "  3. PAYLOAD — it delivers a clear emotional beat OR a useful "
        "insight/opinion; there is a real reason to watch.\n"
        "  4. LENGTH-FIT — the natural moment is roughly 20-60 seconds long.\n"
        "\n"
        "Rules for your output:\n"
        f"  - Return roughly {target} candidates (about 2x the {max_clips} "
        "requested), ranked best-first. A later step dedups overlaps and keeps "
        f"the top {max_clips}, so over-supplying distinct moments helps.\n"
        "  - Give `start` and `end` in SECONDS as floats, on the same scale as "
        "the transcript timestamps shown below (e.g. 73.5 — NOT mm:ss). Pick cut "
        "points at natural sentence boundaries; aim for 20-60 second moments.\n"
        "  - Set `score` to your honest 0.0-1.0 confidence that the clip is "
        "postable as-is. Be calibrated, not generous.\n"
        "  - In `reason`, name which of the Core-4 criteria the moment satisfies "
        "and briefly why.\n"
        "  - Write a punchy `title` (a scroll-stopping hook), a short "
        "`description` (caption), and a few `hashtags`.\n"
        "  - Choose moments spread across the video; do not return overlapping "
        "near-duplicates of the same moment."
    )


def build_user_prompt(transcript: Transcript) -> str:
    """Wrap the rendered transcript in a minimal user-turn instruction."""
    return (
        "Here is the full transcript. Each line is "
        "`[mm:ss-mm:ss] (start_s-end_s) text`. Use the second-based times when "
        "reporting `start`/`end`.\n"
        "\n"
        f"{format_transcript(transcript)}"
    )
