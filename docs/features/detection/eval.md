# Detection eval — the Phase-2 go/no-go gate

_Protocol + results log for `clipper detect --eval`. Owns the project's core
bet: does the AI surface clips a human agrees are postable?_

## Purpose

This is the **go/no-go gate for Phase 2 (detection)** — the thing v1 lives or
dies on (`docs/PROJECT_BRIEF.md`, `CLAUDE.md`). Cropping, captions, and export
are "good enough"; **detection quality is the bet.** The deliverable of this
phase is not "code that calls Claude" — it is a **passed gate**: proof, on a
real authorized hour, that detection surfaces clips a human judges postable.

`clipper detect --eval` is the *build* side of that gate: it runs the real
detection path but **persists nothing** and prints a scannable report (one block
per candidate: `mm:ss-mm:ss` timecode + duration, `score`, the Core-4 `reason`,
the `title`, and the locally derived transcript excerpt), with a header tagging
the run with provider / model / `PROMPT_VERSION` / source id. The operator reads
that report and scores it against the rubric below (task **T6**).

## The Core-4 rubric (the definition of "postable")

A candidate is **postable** iff it satisfies **all four** criteria. The
detection prompt (`src/clipper/detect/prompt.py`) instructs the model to optimize
for exactly these and to name which it hits in each candidate's `reason`, so the
human's bar and the model's target are the same by construction — the eval is a
fast "does the clip actually deliver what the model claimed?" check.

1. **Hook** — grabs attention in the first ~2 seconds.
2. **Self-contained** — lands on its own, without the surrounding video; no "as
   I said earlier" dependency.
3. **Payload** — delivers a clear emotional beat **or** a useful insight/opinion;
   there is a real reason to watch.
4. **Length-fit** — the natural moment is roughly 20–60 s, not cut off
   mid-thought.

**Postable Y/N:** record Y only when all four pass; any failed criterion → N.

## The threshold (the gate)

Score the **top 5** candidates. Then:

- **≥ 3 of the top 5 postable → PASS.** The detection bet is proven; **Phase 3
  (render) is unblocked.**
- **< 3 postable → revise.** Edit `src/clipper/detect/prompt.py`, **bump
  `PROMPT_VERSION`** (so the log stays attributable to an exact prompt revision),
  and re-run. Append a new results-log row each iteration.

This mirrors the v1 product bar (3–5 postable clips per authorized hour) exactly.

_Diagnostic escape hatch:_ when a run **fails**, optionally re-run with a higher
`--max-clips` to inspect whether good candidates sat just outside the top 5 —
this tells you whether the problem is **ranking** or **detection**. The gate
itself is always judged on the top 5.

## Gate requirement — the real transcript must come from the 8 GB Air

The transcript scored at the gate is **not** any convenient transcript. It MUST
come from ingesting **one real ~1-hour authorized video on the 8 GB M1 Air**
(the production target, not the build Pro) with the **default `small` Whisper
model** and worker **concurrency = 1**. While that ingest runs, record:

- **RAM headroom** observed on the idle 8 GB Air (e.g. via Activity Monitor /
  `vm_stat`) — confirm Whisper at `small` leaves the machine usable.
- **Wall-clock** for the full ingest (probe → audio → transcribe → persist).

**This same pass discharges the still-owed Phase-1 sizing validation** (a real
1-hour run on the Air was owed from ingest-transcribe) — record both the
Phase-1 sizing numbers and the Phase-2 gate verdict here, in one go.

Then run the gate **live** against that transcript:

```sh
clipper detect <source_id> --eval --provider claude   # needs ANTHROPIC_API_KEY
```

Detection itself is a **cloud call** (near-zero local RAM), so it runs fine on
the Air; the Air constraint bites on the *ingest* that produces the transcript,
not on detection.

## How to run

```sh
# The gate (real bet): live Claude/Opus judgment. Needs ANTHROPIC_API_KEY set.
clipper detect <source_id> --eval --provider claude

# Persists NOTHING — re-run freely while iterating prompt.py + PROMPT_VERSION.
# Default provider is claude, so `clipper detect <id> --eval` is equivalent.
```

**FREE dev sketch (does NOT substitute for the gate):** an OpenAI-compatible run
against a local Ollama server validates the *plumbing* and gives a rough quality
sketch at zero API cost on the build machine —

```sh
clipper detect <source_id> --eval --provider openai-compat   # local Ollama, no key
```

The local model is a dev/test convenience on the build Pro only; it is **not**
the production path and does **not** run on the Air. A passing Ollama sketch
de-risks the gate but **does not replace the `claude-opus-4-8` judgment the gate
actually measures** (ADR-0001). Score the gate on the `--provider claude` run.

`--mock` (offline, deterministic) exercises only the formatting/plumbing — it
makes no quality judgment and is not valid for the gate.

## Results log

One row per eval run. Bump `PROMPT_VERSION` whenever `prompt.py` changes; the
gate verdict for a row is PASS when `postable /5` ≥ 3, otherwise REVISE.

| date | prompt_version | provider/model | source (duration) | postable /5 | verdict | notes |
| ---- | -------------- | -------------- | ----------------- | ----------- | ------- | ----- |
| 2026-06-22 | detect-v1 | openai-compat / qwen2.5:7b | synthetic demo (214 s) | n/a — dev sketch | DEV-SKETCH | Free Ollama plumbing validated end-to-end via `clipper detect --eval`: 5 candidates, correctly surfaced the hook / "one more email" insight / productivity hot-take / emotional beat over the filler. 7B time precision imperfect (hot-take start landed one segment late) — expected for a small local model; **not a gate verdict.** The real gate is `--provider claude` on a real ~1-hr Air-ingested transcript. |
| 2026-06-23 | detect-v1 | openai-compat / gemini-2.5-flash | synthetic "easy" (214s, planted gems) | 4/5 postable | DEV-SKETCH | Found the 4 strong moments (emotional beat, quit/email hook, "one more email" insight, productivity hot-take) with accurate snapped times; correctly scored the filler "technical difficulties" low (0.60). Frontier PROXY, not Opus. |
| 2026-06-23 | detect-v1 | openai-compat / gemini-2.5-flash | synthetic "hard" (610s, subtle + bait) | 5/5 real gems | DEV-SKETCH | Surfaced 5 subtle buried gems (consistency/"two sentences", discipline-is-small, feedback-vs-hug, burnout-isn't-cinematic, measuring a good day); correctly REJECTED a planted generic time-blocking "tip" + all filler/sponsor/logistics. Frontier PROXY, not Opus. |

The two `gemini-2.5-flash` rows above were run for **free** via Google AI Studio's
OpenAI-compatible endpoint (`https://generativelanguage.googleapis.com/v1beta/openai`,
`--provider openai-compat`) — a frontier-model **proxy** that exercises the real
detection path at zero cost on the build machine. `gemini-2.0-flash` /
`gemini-flash-latest` were **503-throttled** on the free tier while
`gemini-2.5-flash` had capacity (which is exactly what motivated the new
transient-status retry in `OpenAICompatDetector`). These results **de-risk the
bet** — a frontier model surfaces the planted gems and rejects the bait on both an
easy and a deliberately hard synthetic transcript — **but they do NOT replace
T6**: the official gate is still `claude-opus-4-8` on a real ~1-hr authorized
transcript ingested on the 8 GB Air.
