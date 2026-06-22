# Feature design: ingest-transcribe (v1 Phase 1)

> Sliced from the project brief — **not** re-grilled. Authoritative scope and
> rationale live in [`docs/PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md); the full
> task graph is [`docs/features/v1/progress.md`](../v1/progress.md). This feature
> is the **Phase 1** slice (tasks T1–T5).

## Goal

Take a local video belonging to **one authorized creator** and turn it into a
stored, timestamped transcript — gated so that nothing is processed without a
permission record on file. This is the foundation the detection bet (Phase 2)
builds on.

## In scope (T1–T5)

1. **T1** — Consent records: `creator add` + `permission grant` (with stored authorization file).
2. **T2** — Permission-gated `source add` (refuse registration without an active permission).
3. **T3** — ffprobe probe + 16 kHz mono audio extraction (on the Phase 0 ffmpeg wrapper).
4. **T4** — faster-whisper transcriber (`small`/`int8` from config) + transcript JSON persistence.
5. **T5** — `clipper ingest <source_id>` pipeline: probe → audio → transcribe as a sequential Job (concurrency = 1), with stage/progress tracking and error capture; gate re-checked.

## Acceptance (feature-level)

- WHEN `clipper source add` is run for a creator **without** an active permission record, the system SHALL refuse and create no Source row.
- WHEN `clipper ingest <source_id>` is run on a permitted source, the system SHALL produce a stored, segment-timestamped transcript and populate the Source's duration/resolution/transcript_path.
- WHEN a pipeline stage fails, the Job SHALL be marked `error` with the failing stage recorded, without crashing the process.

## Non-goals (later features)

- Clip **detection** (Claude) — Phase 2 (T6–T9), the next pipeline run.
- **Render** (cut / 9:16 / captions), review UI, export — Phases 3–5.
- No posting, OAuth, or multi-creator (v1 anti-goals).

## Constraints

Runtime target is the **8 GB M1 Air**: default Whisper `small`, worker
**concurrency = 1** (Whisper and ffmpeg must not run at once). Transcription is
CPU-only on Mac; `faster-whisper` installs via the `[transcribe]` extra, and
ffmpeg must be present (`brew install ffmpeg`). Validate a real run on the Air
before declaring the feature done.

## Verification

Unit tests for pure logic (permission gate, probe parsing, transcript
serialization, stage ordering/errors with a mock transcriber). Integration tests
that actually probe/extract/transcribe a short synthetic `lavfi` fixture are
marked and skipped when ffmpeg / faster-whisper are unavailable.
