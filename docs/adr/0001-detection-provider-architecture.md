# 1. Detection provider architecture

- Status: accepted
- Date: 2026-06-22

## Context

Detection is the whole bet of this product (`CLAUDE.md`, `docs/PROJECT_BRIEF.md`):
an LLM reads a timestamped transcript and returns the handful of genuinely
clip-worthy moments. Phase 2 (`docs/features/detection/`) implements this behind
the `Detector` protocol scaffolded in `src/clipper/detect/base.py`
(`CandidateClip`, `Detector.detect(transcript, *, max_clips)`). Several design
choices are load-bearing and worth recording before the provider code lands.

The constraining runtime is an idle **8 GB M1 Air** (not the 24 GB build Pro).
Detection must not blow that budget.

## Decision

1. **Single-shot, whole-transcript detection.** One request carries the entire
   transcript; the model sees the whole piece and picks the best moments across
   it (no chunking/windowing). A ~1-hour transcript is ~35k tokens worst case —
   well within the standard 200k context; the 1M window only matters for
   multi-hour sources. Global context beats windowing for "find the best N
   moments."

2. **Structured output via tool-use.** The canonical provider (`ClaudeDetector`,
   Anthropic SDK) forces a single tool call whose `input_schema` mirrors
   `CandidateClip[]`, rather than parsing free-text JSON. `prompt.py` owns the
   Core-4 instructions and a provider-agnostic candidate JSON schema.

3. **Deterministic by default; `temperature` handled conditionally.**
   `detector_temperature` defaults to `0.0`. The canonical `claude-opus-4-8` does
   **not** accept a `temperature` parameter (per the claude-api reference — it was
   removed on Opus 4.7/4.8 and Fable), so the Claude provider **omits**
   `temperature` at the default and forwards it only when explicitly set `> 0`
   (where it still applies to the OpenAI-compatible provider). Determinism for the
   iterative eval therefore rests on the tight prompt + forced tool-use rather than
   a sampling knob — which is also exactly what those models require.

4. **Postprocess is shared, pure functions** (`detect/postprocess.py`):
   drop invalid (reversed/zero-length) ranges → snap rough times to transcript
   segment boundaries → clamp to 20–60 s → drop degenerate → dedup candidates
   overlapping > 50% (keep higher score, globally) → rank by score.
   Provider-independent and table-testable; every provider routes through it so
   model sloppiness never reaches the database.

5. **`transcript_excerpt` is derived locally**, by slicing the transcript
   segments overlapping `[start, end]` — never echoed by the model. The stored
   excerpt is therefore always faithful to what was actually said.

6. **`anthropic` is a core dependency** (already in `pyproject.toml`), not an
   optional extra. Detection is core to v1; there is no build of the tool that
   doesn't want it.

7. **Two providers behind one protocol.** Production is the cloud
   `ClaudeDetector` (`claude-opus-4-8`) — a network call with near-zero local RAM,
   so it fits the 8 GB Air. For zero-cost development and to exercise the full
   path end-to-end, an `OpenAICompatDetector` (using the already-present `httpx`,
   no new dependency) targets any OpenAI-compatible chat-completions endpoint —
   **Ollama** locally (free, no key) or a keyed cloud endpoint. Both share
   `prompt.py` and `postprocess.py`. The local model is a **dev/test convenience
   on the build Pro only**; it is not the production path and does not run on the
   Air, and a local-model eval does **not** substitute for the `claude-opus-4-8`
   go/no-go judgment.

## Consequences

- The pipeline and persistence layers stay provider-agnostic: swapping or adding
  a detector (local LLM, a different cloud model) touches only a `Detector`
  implementation, never the service/CLI/eval.
- Tests use `MockDetector` and canned provider responses — **no live API calls in
  CI, no key required.** Live paths are exercised only by humans: the free Ollama
  sketch and the real Opus go/no-go (T6).
- Detection quality is owned by `prompt.py` (versioned via `PROMPT_VERSION`) and
  iterated against the eval, not by the plumbing — which is exactly where the
  product's effort should concentrate.
- Determinism (`temperature=0`) makes the eval reproducible but means the model
  will not "explore" alternative cuts; acceptable for v1, revisit if the gate
  stalls.
- This ADR realises the "cloud LLM detection behind a provider interface"
  decision reserved as ADR-001 in ADR-0000.
