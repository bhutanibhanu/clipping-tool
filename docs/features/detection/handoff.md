# Feature Handoff: detection (Phase 2)

## Goal
Given an ingested source's timestamped transcript, an LLM reads the whole thing and returns a short ranked list of the best short-form moments (times, score, reason, ready-to-edit copy), persisted as pending `Clip` rows — plus a `--eval` go/no-go harness. This is the project's core bet: detection quality.

## Files changed
```
docs/adr/0001-detection-provider-architecture.md |  81 ++  (new ADR)
docs/features/detection/{design,progress,eval}.md, state.json
pyproject.toml                                   |   9     (gate fix: pins + mypy override)
src/clipper/cli.py                               | 124 ++  (clipper detect [--provider --mock --max-clips --eval])
src/clipper/config.py                            |  18 ++  (detector_temperature, detector_max_clips, openai_*)
src/clipper/detect/base.py                       |   9 ++  (DetectorConfigError)
src/clipper/detect/postprocess.py                | 186 ++  (pure snap/clamp/drop/dedup/rank)
src/clipper/detect/prompt.py                     | 180 ++  (Core-4 prompt + shared schema + PROMPT_VERSION)
src/clipper/detect/claude.py                     | 170 ++  (ClaudeDetector, tool-use)
src/clipper/detect/openai_compat.py              | 299 ++  (OpenAICompatDetector, response_format json_schema)
src/clipper/detect/service.py                    | 173 ++  (make_detector, excerpt_for, detect_for_source)
src/clipper/detect/eval.py                       |  89 ++  (format_eval_report)
src/clipper/transcribe/whisper_local.py          |   2     (gate fix: drop misfiring inline ignore)
tests/test_detect_{postprocess,claude,openai_compat,service,eval}.py + test_transcribe_store.py
22 files changed, +3213 / -3
```

## How to run
```sh
cd "/Users/ray/dev/clipping tool-detection"
uv pip install -e ".[dev,transcribe]"            # already installed in .venv
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest -q

# Detection CLI (needs an ingested source with a transcript):
.venv/bin/clipper detect <source_id> --mock                       # offline, persists pending clips
.venv/bin/clipper detect <source_id> --eval --provider openai-compat   # FREE local Ollama eval (no key)
.venv/bin/clipper detect <source_id> --eval --provider claude          # the real gate (needs ANTHROPIC_API_KEY)
```

## Expected behavior
- `detect <id>` persists 1..max_clips pending `Clip` rows (score/reason/title/description/hashtags + locally-derived `transcript_excerpt`); refuses if the source has no transcript.
- `--eval` prints a scannable top-5 report (timecode/score/Core-4 reason/title/excerpt, attributable header) and persists NOTHING.
- `--provider {claude,openai-compat,mock}`; `--mock` is a shortcut. Unset `ANTHROPIC_API_KEY` on the claude path → clear `DetectorConfigError`, not a raw SDK error.
- Providers issue ONE request over the whole transcript, parse structured output → `CandidateClip[]`, run shared postprocess (snap to segment boundaries, clamp 20–60s, drop invalid, dedup >50% overlap, rank by score), return top N.

## Test plan
- **Automated (137 pass, no network/key):** postprocess (29, table-driven edges), claude (14, canned tool-use + unset-key + malformed), openai_compat (16, canned response_format/tool_calls/content + transport errors), service (13, MockDetector persistence + excerpt + refusal + selector), eval (7, formatter + `--eval` persists-nothing). CI runs `.[dev]`; whisper integration tests skip cleanly.
- **Manual done:** free Ollama `qwen2.5:7b` run end-to-end via the CLI — 5 candidates, found the planted clippable moments; recorded in `eval.md` as a DEV-SKETCH. Noted 7B time imprecision (expected).
- **Manual OUTSTANDING (T6, human):** the real go/no-go on a ~1-hr authorized transcript ingested **on the 8 GB M1 Air**, scored with `--provider claude`. Blocks Phase 3.

## Known risks
- **The bet itself:** detection quality on real content with Opus is unproven until T6 (by design — the eval exists to measure it cheaply before render work).
- **Live Claude path** is exercised only manually (no key in CI). Parsing is defensive (malformed → `[]`), but the exact Opus tool-use response shape is validated only at T6.
- **`temperature` on Opus 4.8:** the model rejects the param; provider omits it at the 0.0 default (forwards only if >0). If a future model needs it, revisit.
- Greedy dedup in postprocess is order-sensitive on 3-way overlaps (rare with ~10 candidates); ranking still applies.

## Open questions
- Final prompt wording is the iterable artifact (versioned by `PROMPT_VERSION`); T6 drives it.
- Whether to also persist on `--eval` (currently no, to keep prompt-iteration runs clean) — deferred to the review-UI phase if needed.
