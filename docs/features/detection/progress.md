# Progress: detection

_Plan generated 2026-06-22 from [`design.md`](design.md) · 7 tasks · T1–T5 + T3B buildable, T6 = human go/no-go gate_
_2026-06-22 scope update: added **T3B** — a free OpenAI-compatible (Ollama/local) provider behind the same `Detector` protocol, so the eval can run end-to-end at zero API cost on the dev machine._

Design source: [`docs/features/detection/design.md`](design.md). This is **Phase 2 — the
detection bet**. Scope **ends at persisted pending `Clip` rows + a recorded eval verdict**;
no cut/render/reframe/caption/UI/export (those are post-gate phases). Reuses the existing
seams on this branch — `detect/base.py` (`CandidateClip`, `Detector`), `detect/mock.py`
(`MockDetector`), `db/models.py::Clip` — and the Phase-1 `clipper ingest <id>` that produces
a timestamped `Transcript`.

Verified against the repo at plan time: `anthropic>=0.40` is already a **core** dependency
(no `[detect]` extra), `Settings.detector_model` already defaults to `claude-opus-4-8`, and
a ~1-hour transcript (~35k tokens worst case) fits the **standard 200k context** — the 1M
window only matters for multi-hour sources.

**Free-testing strategy (T3B):** production detection is a **cloud Claude call** (near-zero
local RAM → fits the 8 GB M1 Air). To validate the *plumbing* and get a *quality sketch*
without paid API spend, T3B adds an `OpenAICompatDetector` (uses the already-present `httpx`,
no new dep) that targets any OpenAI-compatible endpoint — **Ollama** (`localhost:11434/v1`,
free/local, no key) for dev testing, or OpenRouter/Groq/etc. with a key. It shares
`prompt.py` (Core-4) and `postprocess.py` with the Claude provider. **The local model is a
dev/test convenience on the build Pro only — it is NOT the production path and does not run
on the Air.** A free Ollama eval de-risks T6 but does not replace it: the real bet is
`claude-opus-4-8`'s judgment specifically.

## Task list
- [x] T1 — ADR-0001: detection provider architecture
- [x] T2 — Postprocess (pure: snap + clamp + drop + dedup)
- [x] T3 — Claude `Detector` provider + Core-4 prompt
- [x] T3B — OpenAI-compatible provider (free local/dev testing via Ollama)
- [x] T4 — Detection persistence + `clipper detect <source_id>`
- [ ] T5 — Eval harness (`clipper detect --eval`)
- [ ] T6 — 🚦 GO/NO-GO gate run (human judgment, on the 8 GB Air)

Legend: `[ ]` todo · `[>]` in progress · `[x]` done (short sha) · `[!]` blocked

---

## Tasks

### T1 — ADR-0001: detection provider architecture
- **Goal:** Record the load-bearing detector decisions before any provider code, per the repo's ADR convention.
- **Depends on:** none
- **Files (expected):** `docs/adr/0001-detection-provider-architecture.md`
- **Acceptance:**
  - WHEN T1 is complete, `docs/adr/0001-detection-provider-architecture.md` SHALL exist with a status of `Accepted` and a date, following the template set by `docs/adr/0000-record-architecture-decisions.md`.
  - The ADR SHALL record each decision with its rationale: single-shot whole-transcript detection (standard 200k context suffices for the 1-hr target; 1M only for multi-hour); structured output via Claude **tool-use** (a forced tool call whose `input_schema` mirrors `CandidateClip`); `temperature=0` for repeatable eval comparison; postprocess (snap/clamp/dedup) as **shared pure functions**; `transcript_excerpt` **derived locally**, not model-echoed; that `anthropic` is **already a core dependency** (no `[detect]` extra); and the **two-provider design** (canonical cloud `ClaudeDetector` + an `OpenAICompatDetector` for free local/dev testing, both behind `Detector`, sharing prompt + postprocess; local model is dev-only, production stays cloud-Claude on the Air).
  - The ADR SHALL NOT contradict ADR-0000 or `CLAUDE.md`.
- **Tests:** none — documentation.
- **Status:** done

### T2 — Postprocess (pure: snap + clamp + drop + dedup)
- **Goal:** Turn a detector's raw, rough time-ranges into clean, ranked, non-overlapping candidates via pure functions — independent of any provider.
- **Depends on:** T1
- **Files (expected):** `src/clipper/detect/postprocess.py`, `tests/test_postprocess.py`
- **Acceptance:**
  - WHEN a candidate's `start`/`end` fall mid-segment, the system SHALL snap them to the enclosing transcript segment boundaries.
  - WHEN a snapped candidate is shorter than 20 s, the system SHALL extend it (within `[0, source_duration]`) to ≥ 20 s; WHEN longer than 60 s, the system SHALL trim it to ≤ 60 s.
  - WHEN `end ≤ start` after snapping/clamping, the system SHALL drop the candidate.
  - WHEN two candidates' overlap ratio (intersection ÷ shorter candidate's duration) exceeds 0.5, the system SHALL keep the higher-scored one and drop the other.
  - WHEN postprocessing completes, the system SHALL return the surviving candidates ranked by descending `score`.
- **Tests:** table-driven unit tests per rule + edges — start-of-file, end-of-file, exact-boundary snap, full vs partial (>50% and <50%) overlap, equal-score overlap tiebreak, `end≤start` drop. Pure functions, no I/O, no model.
- **Status:** done (29 tests; half-open boundary snapping, strict >0.5 overlap, deterministic tiebreak)

### T3 — Claude `Detector` provider + Core-4 prompt
- **Goal:** Implement the `Detector` protocol against Claude with one structured tool-use request over the full transcript, optimizing for the Core-4 rubric.
- **Depends on:** T2
- **Files (expected):** `src/clipper/detect/prompt.py`, `src/clipper/detect/claude.py`, `src/clipper/config.py` (add `detector_temperature`), `tests/test_detect_claude.py`
- **Acceptance:**
  - WHEN `ClaudeDetector().detect(transcript, max_clips=n)` is called with `ANTHROPIC_API_KEY` set, the system SHALL issue exactly **one** Messages request carrying a single tool whose `input_schema` mirrors `CandidateClip[]`, parse the tool call, apply T2 postprocess, and return ≤ n candidates ranked by descending score.
  - The provider SHALL request more raw candidates than `n` (≈ 2n) so that ≥ n **distinct** candidates survive dedup when the source allows.
  - `prompt.py` SHALL instruct the model to optimize for the **Core-4** (hook · self-contained · payload · length-fit) and to state which criteria each candidate satisfies in its `reason`, and SHALL expose a `PROMPT_VERSION` constant and a provider-agnostic candidate JSON schema (shared with T3B).
  - WHEN `ANTHROPIC_API_KEY` is unset, the system SHALL raise a clear configuration error (not a raw SDK exception).
  - WHEN the response carries no tool call, or malformed candidate JSON, the system SHALL return `[]` and log a warning, and SHALL NOT raise.
  - The request SHALL use `Settings.detector_temperature` (default `0.0`) and `Settings.detector_model`.
- **Tests:** unit only — parse a **canned** tool-use response → `CandidateClip[]` (post-processed); unset key → config error; no-tool-call / malformed → `[]`. **No live API call — the network must not be touched in CI**; the live path is exercised in T3B (free) and T6 (Opus).
- **Status:** done (14 tests; injectable client, forced tool-use, anthropic 0.111; temperature omitted for Opus 4.8 per claude-api)

### T3B — OpenAI-compatible provider (free local/dev testing)
- **Goal:** A second `Detector` that runs against any OpenAI-compatible chat-completions endpoint (Ollama locally for free, or a keyed cloud endpoint) so the full detection path can be exercised end-to-end at zero cost — without touching the canonical Claude provider.
- **Depends on:** T3 (reuses `prompt.py` + the shared candidate schema) and T2 (postprocess)
- **Files (expected):** `src/clipper/detect/openai_compat.py`, `src/clipper/config.py` (add `openai_base_url`, `openai_model`, `openai_api_key`), `tests/test_detect_openai_compat.py`
- **Acceptance:**
  - WHEN `OpenAICompatDetector().detect(transcript, max_clips=n)` is called, the system SHALL POST a single `/chat/completions` request (via `httpx`) carrying the Core-4 prompt and a function/tool definition mirroring the shared candidate schema, parse `tool_calls` → `CandidateClip[]`, apply T2 postprocess, and return ≤ n ranked candidates.
  - The endpoint, model, and (optional) key SHALL come from `Settings.openai_base_url` / `openai_model` / `openai_api_key`; WHEN no key is set, the request SHALL still proceed (Ollama needs none).
  - WHEN the response has no tool call / malformed JSON / a transport error, the system SHALL return `[]` and log a warning, and SHALL NOT raise.
  - The provider SHALL NOT be used in CI tests against a live endpoint.
- **Tests:** unit only — parse a **canned** OpenAI-style `tool_calls` response → `CandidateClip[]` (post-processed); malformed / no-tool-call → `[]`; transport error (monkeypatched httpx) → `[]`. No network in CI.
- **Status:** done (16 tests; httpx, shared prompt/schema, JSON-schema `response_format` + content/tool-call parse, injectable client; **LIVE-VERIFIED** against Ollama qwen2.5:7b — found 4/4 planted clips, skipped filler. Note: forced function-calling made the 7B model fill the wrong field, so structured output uses `response_format` json_schema.)

### T4 — Detection persistence + `clipper detect <source_id>`
- **Goal:** Run detection on an ingested source and persist the ranked candidates as pending `Clip` rows, exposed as a CLI command with selectable provider.
- **Depends on:** T3, T3B
- **Files (expected):** `src/clipper/detect/service.py`, `src/clipper/cli.py`, `src/clipper/config.py` (add `detector_max_clips`), `tests/test_detect_service.py`
- **Acceptance:**
  - WHEN `clipper detect <source_id>` runs on a source that has a transcript, the system SHALL persist `1..max_clips` `Clip` rows with `status=pending`, populated `start_seconds`/`end_seconds`/`score`/`reason`/`title`/`description`/`hashtags`, and a `transcript_excerpt` **derived locally** by concatenating transcript segment text overlapping `[start,end]`.
  - All persisted clip times SHALL lie within `[0, Source.duration_seconds]`.
  - WHEN the source has no transcript, the system SHALL refuse with a clear error and persist no clips.
  - The provider SHALL be selectable: `--provider {claude,openai-compat,mock}` (default `claude`); `--mock` remains a shortcut for `mock`. `openai-compat` targets `Settings.openai_base_url` (e.g. Ollama) for free/local runs. `max_clips` SHALL default from `Settings.detector_max_clips` (`5`).
- **Tests:** with `MockDetector` — detect persists N pending clips with valid fields and a non-empty derived excerpt; all times within source duration; no-transcript refusal; provider selection resolves to the right class. The excerpt-derivation helper gets a direct unit test. (Live paths covered manually: T3B free, T6 Opus.)
- **Status:** done (13 tests; `make_detector` selector w/ lazy imports, `excerpt_for`, `detect_for_source(persist=)`, CLI `detect --provider/--mock/--max-clips` matching `ingest` error style)

### T5 — Eval harness (`clipper detect --eval`)
- **Goal:** A human-scannable eval view plus a results log so the operator can judge detection quality and iterate the prompt — the build-side of the go/no-go gate.
- **Depends on:** T4
- **Files (expected):** `src/clipper/cli.py` (`--eval` flag), `src/clipper/detect/eval.py` (formatter), `docs/features/detection/eval.md` (protocol + results template), `tests/test_detect_eval.py`
- **Acceptance:**
  - WHEN `clipper detect <source_id> --eval` runs, the system SHALL print the **top 5** candidates, each showing `mm:ss–mm:ss` timecode, `score`, the Core-4 `reason`, the `title`, and the derived transcript excerpt, in a fixed scannable layout.
  - WHEN `--eval` is used, the system SHALL **NOT** persist `Clip` rows (so repeated prompt-iteration runs do not accumulate pending clips).
  - The system SHALL surface the active `PROMPT_VERSION` and the provider/model used so eval output is attributable.
  - `docs/features/detection/eval.md` SHALL contain the gate protocol (Core-4 rubric, the ≥ 3-of-5 threshold, the requirement that the real gate transcript come from a ~1-hr ingest on the 8 GB Air) and an empty results-log table keyed by `PROMPT_VERSION` + provider.
- **Tests:** smoke-test the formatter against `MockDetector` output — asserts 5 rows render with timecodes, score, title, and excerpt. No network.
- **Status:** todo

### T6 — 🚦 GO/NO-GO gate run (human judgment)
- **Goal:** Prove the detection bet on real authorized content before any render work begins.
- **Depends on:** T5
- **Files (expected):** `docs/features/detection/eval.md` (filled in with the run's results)
- **Acceptance:**
  - WHEN one real ~1-hour authorized video is ingested **on the 8 GB M1 Air** with the default `small` Whisper model, the operator SHALL record observed RAM headroom and wall-clock latency in `eval.md` — **this discharges the still-owed Phase-1 sizing validation** in the same pass.
  - WHEN `clipper detect <id> --eval` is run live (real `ANTHROPIC_API_KEY`, `--provider claude`) on that transcript, the operator SHALL score each of the top 5 against the Core-4 rubric (pass/fail per criterion + a postable Y/N) in `eval.md`, tagged with `PROMPT_VERSION`.
  - **GATE — WHEN ≥ 3 of the top 5 are judged postable, the feature SHALL be marked PASS and Phase 3 (render) unblocked; OTHERWISE the operator SHALL revise `prompt.py`, bump `PROMPT_VERSION`, and re-run.**
  - _De-risking (optional, free): a `--provider openai-compat` run against local Ollama can pre-validate the plumbing and give a rough quality sketch, but does NOT substitute for the Opus judgment this gate measures._
- **Tests:** none — human-judgment gate (the formatter is covered by T5).
- **⛔ Blocks:** Phase 3 (render) does not begin until this gate passes.
- **Status:** todo
