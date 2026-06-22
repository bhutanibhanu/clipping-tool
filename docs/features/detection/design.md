# Feature Design: detection (Phase 2)

_Designed 2026-06-22 via `/grill` · slug `detection` · branch `feat/detection`_
_Source priors: `docs/PROJECT_BRIEF.md`, `docs/features/v1/progress.md` (T6–T9)._

> **This is the project's actual bet.** Cropping, captions, and export are "good
> enough"; detection quality is the thing v1 lives or dies on. The deliverable of
> this feature is not "code that calls Claude" — it's a **passed go/no-go gate**:
> proof, on a real authorized hour, that the AI surfaces clips a human agrees are
> postable.

## Section 1 — The basics

- **Elevator pitch:** Given an ingested source's timestamped transcript, Claude
  reads the whole thing and returns a short ranked list of the best short-form
  moments — with times, a confidence score, a reason, and ready-to-edit copy —
  persisted as pending `Clip` rows for later review.
- **Problem:** Finding the 3–5 genuinely postable moments in an hour of long-form
  video is the expensive, skilled, time-consuming part of clip production. That
  judgment is what we're testing whether an LLM can do well enough to trust.
- **User:** The single operator (the creator's editor/themselves) running
  `clipper` locally on a Mac. No multi-user, no web step in this feature.
- **Success (concrete — the gate):** On a **real ~1-hour authorized transcript**,
  `clipper detect --eval` surfaces the **top 5** candidates and the operator
  judges **≥ 3 of them "postable"** against the Core-4 rubric (below). ≥ 3 → the
  detection bet is proven, proceed to Phase 3 (render). < 3 → iterate the prompt
  and re-run. This mirrors the v1 product bar (3–5 postable clips/hour) exactly.
- **Anti-goals (this feature):** No cut/render/reframe/caption, no review UI, no
  export, no posting. Detection **ends** at persisted pending `Clip` rows + a
  recorded eval verdict. No multi-creator, no local-LLM provider (the `Detector`
  seam keeps that door open; we don't build it).
- **Constraints:**
  - Tests use `MockDetector` — **no live API calls in CI, no key required.** The
    live Claude path is exercised only by the human-run eval (T9).
  - Detection is a **cloud call** (near-zero local RAM) → fits the 8 GB M1 Air.
  - Model `claude-opus-4-8` via `Settings.detector_model`; key from
    `ANTHROPIC_API_KEY` (never committed; `clipper doctor` already reports it).
  - Space-safe paths; new architecture decision → ADR in `docs/adr/`.

## Section 2 — Requirements

### Functional (ranked)
1. **Claude `Detector` provider** — one structured-output request over the whole
   transcript → `list[CandidateClip]`, post-processed and ranked by score.
2. **Postprocess** — pure functions: snap rough times to transcript segment
   boundaries, clamp to 20–60 s, drop invalid, **merge/drop overlapping
   near-duplicates** (keep higher score), then take top `max_clips`.
3. **Persistence + CLI** — `clipper detect <source_id>` maps candidates →
   pending `Clip` rows; `--mock` uses `MockDetector` (offline); refuse if the
   source has no transcript.
4. **Eval / go-no-go harness** — `clipper detect --eval` prints the top 5 in a
   human-scannable format (time, score, reason, title, derived transcript
   excerpt) for rubric judgment; protocol + results live in
   `docs/features/detection/eval.md`.
5. **The Core-4 rubric**, used identically by the human (to judge) and the prompt
   (to optimize) — see Section 3.

### Non-functional
- **Latency/cost:** a single ~13–35k-token Opus call per source (one hour of
  transcript). Sub-minute, well under a dollar — a non-issue for one creator.
- **RAM:** negligible locally (cloud call). The Air constraint applies to the
  *ingest* that produces the eval transcript, not detection itself.
- **Determinism:** `temperature = 0` so prompt iteration A/B is comparable run to
  run. (Not bit-identical, but stable enough to attribute a gate change to the
  prompt, not sampling noise.)
- **Robustness:** unset key → clear config error (not a raw SDK traceback);
  malformed/empty model response → `[]` + a log line, never a crash.
- **Security/data:** transcript text leaves the machine to Anthropic on the live
  path — acceptable (authorized creator content, operator-initiated). No key on
  disk; env only.

### Future (does today's design survive it?)
- **Local-LLM provider** (privacy/offline): drop in behind `Detector`, reuse
  postprocess + service + eval unchanged. ✅ accommodated.
- **Re-detect with a better prompt** after Phase 3 ships: prompt is a versioned
  module; eval log already tracks prompt version → quality. ✅
- **Per-clip transcript-grounded scoring / multi-pass detection:** would change
  the provider internals only, not the seam. ✅

## Section 3 — Architecture (deltas from existing)

### The Core-4 rubric (the definition of "postable")
A candidate is postable iff it has all four:
1. **Hook** — grabs attention in the first ~2 seconds.
2. **Self-contained** — lands without the surrounding video; no "as I said
   earlier" dependency.
3. **Payload** — a clear emotional beat **or** a useful insight/opinion.
4. **Length-fit** — naturally 20–60 s, not cut off mid-thought.

The detection **prompt instructs Claude to find exactly these**, and the
candidate's `reason` should state which it satisfies — so the operator's eval is
a fast "does the clip actually deliver what the model claimed?" check. Human bar
== model target, by construction.

### Data flow
```
ingested Source (has transcript_path)
  └─ clipper detect <id>
       ├─ load Transcript (segments: start/end/text)
       ├─ Detector.detect(transcript, max_clips=5)        # Claude or --mock
       │    ├─ build prompt (full transcript + Core-4 instructions)
       │    ├─ one structured-output (tool-use) request → raw candidates
       │    ├─ postprocess(raw, segments, source_duration):
       │    │     drop-invalid → snap → clamp(20–60s) → drop(end≤start) → dedup(>50% overlap)
       │    └─ rank by score desc; take top max_clips
       ├─ derive transcript_excerpt per clip (slice segments in [start,end])
       └─ persist pending Clip rows  (status=pending)
   --eval: same path, but PRINT the top 5 for human rubric judgment
           (and append to eval.md) instead of/in addition to persisting
```

### Stack deltas
- **New dep:** the official `anthropic` SDK (new optional extra, e.g. `[detect]`,
  mirroring the `[transcribe]` pattern; or core dep — decide in ADR).
- **New modules:** `detect/postprocess.py` (pure), `detect/prompt.py` (prompt
  builder + version constant), `detect/claude.py` (`ClaudeDetector`),
  `detect/service.py` (orchestrate + persist), `cli.py` (`detect` command).
- **Reused seams (already on `main`):** `detect/base.py` (`CandidateClip`,
  `Detector`), `detect/mock.py` (`MockDetector`), `db/models.py::Clip`.

### Structured output
Use **Claude tool-use** with an `input_schema` matching `CandidateClip[]` (the
model "reports" candidates via a forced tool call). More reliable than free-text
JSON parsing. The provider requests a **deeper raw list** (~2× `max_clips`) so
that after dedup/drop, 5 *distinct* candidates still survive to surface. → ADR.

### Data model
No schema change. `CandidateClip` → `Clip` maps field-for-field:
`start→start_seconds`, `end→end_seconds`, `score`, `reason`, `title`,
`description`, `hashtags`, `status=pending`. `transcript_excerpt` is **derived**
locally (slice transcript segments overlapping `[start,end]`), **not** echoed by
the model — faithful to what was actually said. `output_path` stays null (render
is a later phase).

### Config (`Settings`)
Add `detector_model` (default `claude-opus-4-8`), `detector_temperature`
(default `0.0`), `detector_max_clips` (default `5`). Key via env
`ANTHROPIC_API_KEY`.

### The eval gate protocol (`eval.md`)
1. **Produce the transcript on the real target:** ingest **one real ~1-hour
   authorized video on the 8 GB M1 Air** with the default `small` Whisper model.
   Record RAM headroom + wall-clock — this **discharges the still-owed Phase-1
   sizing validation** in the same pass.
2. Run `clipper detect --eval <source_id>` (live key). Print top 5 with
   time / score / reason / title / derived excerpt.
3. For each, the operator records Core-4 pass/fail + a postable Y/N in `eval.md`,
   tagged with the **prompt version**.
4. **GATE: ≥ 3 of 5 postable → PASS** (proceed to Phase 3). Otherwise revise
   `detect/prompt.py`, bump the version, re-run, append a new row.
5. **Diagnostic escape hatch:** when a run *fails*, optionally re-run with a
   higher count to inspect whether good candidates sat just outside the top 5
   (informs whether the problem is ranking or detection). Default stays 5.

## Section 5 — Risks & open questions

### Top risks
1. **(Product, existential) Detection isn't good enough — gate fails.** This is
   the whole bet. *Mitigation:* the eval loop is purpose-built to catch it cheaply
   *before* any render investment; prompt is iterable and versioned; failing the
   gate is a valid, designed outcome, not a bug.
2. **(Technical) Model returns sloppy times** (mid-word, overlapping, out of
   bounds). *Mitigation:* postprocess snaps/clamps/drops/dedups; table-driven
   tests on edges (start-of-file, end-of-file, overlaps, end≤start).
3. **(Operational) Live-path fragility** (key unset, rate limit, malformed
   response). *Mitigation:* explicit config error; malformed→`[]`+log; live path
   kept out of CI so the suite never flakes on the network.

### Open questions
- Exact prompt wording (the iterable artifact) — start simple, let the eval loop
  drive it. Not a design-time decision.
- `[detect]` extra vs core dependency for `anthropic` — settle in the ADR.

### Deferred (with triggers)
- Token cost tracking / multi-pass detection — **revisit only if** single-shot
  fails the gate on quality grounds.
- Re-detection workflow (re-run on a source that already has clips) — **revisit
  at Phase 4 (review UI)**, where re-running becomes a user action.

### ADRs to write before code
- **ADR-0001 — Detection provider architecture:** single-shot whole-transcript
  detection; structured output via tool-use; `temperature=0`; postprocess
  (snap/clamp/dedup) as shared pure functions; transcript excerpt derived
  locally; `anthropic` packaged as `[detect]` extra.

## Section 6 — Roadmap

Refines v1-plan T6–T9; `/plan` will decompose into acceptance-criteria'd tasks.

- **T6 — Postprocess** (`detect/postprocess.py`, pure): snap-to-segment, clamp
  20–60 s, drop invalid, dedup >50% overlap (keep higher score). Table-driven
  unit tests. _No deps._
- **T7 — Claude provider** (`detect/claude.py` + `detect/prompt.py`): tool-use
  structured request over full transcript, Core-4 prompt, parse → postprocess →
  rank → top `max_clips`. Unit tests parse canned tool output; missing key →
  config error; malformed → `[]`. _No live call in CI._ _Deps: T6._
- **T8 — Persistence + CLI** (`detect/service.py`, `cli.py`): `clipper detect
  <id>` → pending `Clip` rows (excerpt derived); `--mock`; refuse if no
  transcript. Tests with `MockDetector`. _Deps: T7._
- **T9 — 🚦 Go/no-go eval** (`clipper detect --eval`, `eval.md`): real ~1-hour
  ingest **on the 8 GB Air** → live detect → Core-4 rubric scoring → gate
  decision. Eval formatter smoke-tested vs `MockDetector`; the judgment itself is
  human. **⛔ Blocks Phase 3.** _Deps: T8 + a real authorized source._

### First-sprint task list (ordered)
1. ADR-0001 (detector architecture).
2. T6 postprocess + tests.
3. T7 Claude provider + prompt + unit tests.
4. T8 service + `clipper detect` + tests.
5. T9 eval harness; then the **human gate run on the Air**.
