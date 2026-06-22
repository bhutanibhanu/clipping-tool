# Progress: v1

_Plan generated 2026-06-22 from `docs/PROJECT_BRIEF.md` · 16 tasks · supervised build_

Design source: [`docs/PROJECT_BRIEF.md`](../../PROJECT_BRIEF.md). Phase 0 (scaffold)
is already complete and green. This plan covers Phases 1–2 in depth and sketches
Phases 3–5 (to be re-planned after the T9 go/no-go gate).

CLI shape: registration (`source add`, where the permission gate fires) is split
from processing (`ingest <source_id>`) — register once under a creator+permission,
then process by id.

## Task list
- [ ] T1 — Consent records: `creator add` + `permission grant`
- [ ] T2 — Permission-gated `source add`
- [ ] T3 — ffprobe probe + audio extraction
- [ ] T4 — faster-whisper transcriber + transcript persistence
- [ ] T5 — `clipper ingest <source_id>` pipeline wiring
- [ ] T6 — Clip post-processing (clamp + snap)
- [ ] T7 — Claude `Detector` provider
- [ ] T8 — Detection persistence + `clipper detect <source_id>`
- [ ] T9 — 🚦 GO/NO-GO GATE: detection-quality eyeball-eval
- [ ] T10 — Cut stage _(sketch)_
- [ ] T11 — Blurred-pad 9:16 reframe _(sketch)_
- [ ] T12 — Burned phrase-level captions _(sketch)_
- [ ] T13 — Background job runner + progress endpoints _(sketch)_
- [ ] T14 — Review UI (list + video + approve/reject) _(sketch)_
- [ ] T15 — Permission/Creator CRUD UI + auth-file upload _(sketch)_
- [ ] T16 — Export approved clips + provenance _(sketch)_

Legend: `[ ]` todo · `[>]` in progress · `[x]` done (short sha) · `[!]` blocked

---

## Tasks

### T1 — Consent records: `creator add` + `permission grant`
- **Goal:** Seed a Creator and an active PermissionRecord (with a stored authorization file), and expose service lookups; initialize the DB on first write.
- **Depends on:** none
- **Files (expected):** `src/clipper/catalog.py` (creator create/list), `src/clipper/permissions/service.py` (grant + `active_permission_for`), `src/clipper/db/session.py` (session context + init-if-absent), `src/clipper/cli.py`, `tests/test_permissions.py`
- **Acceptance:**
  - WHEN `clipper creator add --name <n>` runs, the system SHALL create exactly one Creator row and print its id, creating the SQLite DB under `storage/` if absent.
  - WHEN `clipper permission grant --creator <id> --scope <s> --auth-file <path>` runs and `<path>` exists, the system SHALL persist a PermissionRecord with `status=active` and a recorded `authorization_file_path`.
  - WHEN `--auth-file` points to a missing path, the system SHALL exit non-zero and persist no PermissionRecord.
  - WHEN `active_permission_for(creator_id)` is called, the system SHALL return the active record and SHALL NOT return a `revoked` one.
- **Tests:** service-level — grant creates an active record; missing auth file raises and persists nothing; `active_permission_for` returns active and skips revoked. (CLI exercised via typer `CliRunner`.)
- **Status:** todo

### T2 — Permission-gated `source add`
- **Goal:** Register a local video as a Source only if its creator has an active permission; refuse otherwise.
- **Depends on:** T1
- **Files (expected):** `src/clipper/permissions/service.py` (`require_permission` gate), `src/clipper/catalog.py` (`register_source`), `src/clipper/cli.py`, `tests/test_sources.py`
- **Acceptance:**
  - WHEN `clipper source add --file <v> --creator <id>` runs and the creator has an active PermissionRecord, the system SHALL create a Source row linked to that permission and print its id.
  - WHEN the creator has no active PermissionRecord, the system SHALL raise `PermissionRequiredError`, exit non-zero, and create no Source row.
  - WHEN `<file>` does not exist, the system SHALL exit non-zero and create no Source row.
- **Tests:** gated allow (active) / refuse (none, revoked); missing file refused; created Source references the correct permission_id.
- **Status:** todo

### T3 — ffprobe probe + audio extraction
- **Goal:** Probe duration/resolution and extract a 16 kHz mono WAV for transcription, on top of the Phase 0 ffmpeg wrapper.
- **Depends on:** none
- **Files (expected):** `src/clipper/media/probe.py`, `src/clipper/media/audio.py`, `tests/test_probe.py`, `tests/conftest.py` (synthetic-clip fixture)
- **Acceptance:**
  - WHEN `probe(path)` parses ffprobe JSON, the system SHALL return duration (seconds, float), width, and height.
  - WHEN `extract_audio(src, dst)` runs, the system SHALL produce a 16 kHz mono WAV at `dst` via an argument-list ffmpeg call (no shell string).
  - WHEN ffmpeg/ffprobe is absent, both SHALL raise `FFmpegNotFoundError`.
- **Tests:** unit — `probe` field-mapping from a captured ffprobe JSON string (no ffmpeg needed). Integration — generate a ~10 s `lavfi` test clip, probe + extract, assert WAV exists with expected sample rate; `@pytest.mark.integration`, skipped when ffmpeg is unavailable.
- **Status:** todo

### T4 — faster-whisper transcriber + transcript persistence
- **Goal:** Implement the `Transcriber` protocol with faster-whisper (model/compute from config, `small`/`int8` default) and persist the transcript as JSON, setting `Source.transcript_path`.
- **Depends on:** T3
- **Files (expected):** `src/clipper/transcribe/whisper_local.py`, `src/clipper/transcribe/store.py` (Transcript ⇄ JSON), `tests/test_transcribe_store.py`. Installs the `[transcribe]` extra.
- **Acceptance:**
  - WHEN `WhisperTranscriber().transcribe(audio_path)` runs, the system SHALL return a `Transcript` whose segments each satisfy `start <= end` and non-empty text.
  - WHEN the transcript is saved, the system SHALL write JSON under `storage/` and set `Source.transcript_path`.
  - The model size and compute type SHALL be read from `Settings` (default `small` / `int8`).
- **Tests:** unit — `Transcript`⇄JSON round-trip (no model). Integration — transcribe the synthetic fixture's audio, assert ≥1 segment; `@pytest.mark.integration`, skipped when `faster-whisper`/ffmpeg are unavailable.
- **Status:** todo

### T5 — `clipper ingest <source_id>` pipeline wiring
- **Goal:** Run probe → extract audio → transcribe sequentially as a Job (concurrency = 1), recording stage/progress and capturing stage errors; re-check the permission gate at ingest time.
- **Depends on:** T2, T3, T4
- **Files (expected):** `src/clipper/pipeline/stages.py`, `src/clipper/pipeline/jobs.py`, `src/clipper/cli.py`, `tests/test_pipeline_ingest.py`
- **Acceptance:**
  - WHEN `clipper ingest <source_id>` runs on a permitted source, the system SHALL create a Job, run the three stages in order, set `Job.status=done`, and populate `Source.duration_seconds`, width/height, and `transcript_path`.
  - WHEN the source's permission is missing or revoked at ingest time, the system SHALL refuse and leave no Job in `done`.
  - WHEN a stage raises, the system SHALL set `Job.status=error` with the failing `stage` recorded, and the process SHALL NOT crash.
- **Tests:** unit — stage runner with a mock transcriber + monkeypatched media functions asserts stage order, progress/status transitions, and error capture. Integration — end-to-end on the fixture; skipped without ffmpeg/whisper.
- **Status:** todo

### T6 — Clip post-processing (clamp + snap)
- **Goal:** Pure functions to snap raw model time ranges to transcript segment boundaries and clamp to a 20–60 s window, dropping invalid ranges.
- **Depends on:** none
- **Files (expected):** `src/clipper/detect/postprocess.py`, `tests/test_postprocess.py`
- **Acceptance:**
  - WHEN a candidate is shorter than 20 s, the system SHALL extend it (within source bounds) to ≥ 20 s.
  - WHEN a candidate is longer than 60 s, the system SHALL trim it to ≤ 60 s.
  - WHEN start/end fall mid-segment, the system SHALL snap them to the enclosing segment boundaries.
  - WHEN end ≤ start after snapping, the system SHALL drop the candidate.
- **Tests:** table-driven unit tests for each rule + edges (start of file, end of file, overlapping candidates).
- **Status:** todo

### T7 — Claude `Detector` provider
- **Goal:** Network-backed `Detector` — one structured-output request to `Settings.detector_model`, parsed into `CandidateClip[]`, post-processed via T6, ranked by score.
- **Depends on:** T6
- **Files (expected):** `src/clipper/detect/claude.py`, `src/clipper/detect/prompt.py`, `tests/test_detect_claude.py`
- **Acceptance:**
  - WHEN `ClaudeDetector().detect(transcript, max_clips=n)` is called, the system SHALL issue a single structured-output request, parse `CandidateClip[]`, apply T6, and return ≤ n candidates ranked by descending score.
  - WHEN `ANTHROPIC_API_KEY` is unset, the system SHALL raise a clear configuration error (not a raw SDK exception).
  - WHEN the response is malformed or empty, the system SHALL return `[]` and log, not crash.
- **Tests:** unit — parse canned structured JSON → `CandidateClip[]`; missing-key raises config error; malformed → `[]`. No live API call in the default suite (live path is exercised in T9).
- **Status:** todo

### T8 — Detection persistence + `clipper detect <source_id>`
- **Goal:** Run detection on an ingested source's transcript and persist pending `Clip` rows with score/reason/title/description/hashtags/excerpt.
- **Depends on:** T5, T7
- **Files (expected):** `src/clipper/detect/service.py`, `src/clipper/cli.py`, `tests/test_detect_service.py`
- **Acceptance:**
  - WHEN `clipper detect <source_id>` runs on a source with a transcript, the system SHALL persist 1..max_clips `Clip` rows with `status=pending`, populated score/reason/title/excerpt, and times within `Source.duration_seconds`.
  - WHEN the source has no transcript, the system SHALL refuse with a clear error and persist no clips.
  - WHEN `--mock` is passed, the system SHALL use `MockDetector` (offline, no key); otherwise the Claude provider.
- **Tests:** with `MockDetector` — detect persists N pending clips with valid fields; no-transcript refusal. (Claude path covered manually in T9.)
- **Status:** todo

### T9 — 🚦 GO/NO-GO GATE: detection-quality eyeball-eval
- **Goal:** A repeatable harness to run the live Claude detector on a real authorized transcript and review candidate quality — the explicit gate before any render work.
- **Depends on:** T8
- **Files (expected):** `src/clipper/cli.py` (`clipper detect --eval`), `docs/features/v1/eval.md` (protocol + results log)
- **Acceptance:**
  - WHEN run with a live key on a real ~1-hour authorized transcript, the system SHALL print ranked candidates with timecodes, scores, reasons, and titles for human review.
  - The operator SHALL record in `eval.md` how many surfaced candidates are "genuinely postable."
  - **GATE — WHEN ≥ 3 candidates are judged postable, proceed to Phase 3; OTHERWISE iterate the T7 prompt and re-run.** (Threshold = the v1 success bar.)
- **Tests:** none — this is a human-judgment gate. (The eval formatter gets a smoke test against `MockDetector`.)
- **Status:** todo
- **⛔ Blocks:** T10–T16 do not begin until this gate passes.

---

## Phases 3–5 — sketches (re-plan in depth after the T9 gate)

### T10 — Cut stage _(sketch)_
- **Goal:** Extract the `[start, end]` segment of a source to a working file via ffmpeg.
- **Depends on:** T9 (gate)
- **Acceptance (sketch):** WHEN given a Clip's times, the system SHALL produce a trimmed clip whose duration matches within ±0.1 s. **Re-plan after gate.**
- **Status:** todo (sketch)

### T11 — Blurred-pad 9:16 reframe _(sketch)_
- **Goal:** Reframe a 16:9 clip to 1080×1920 with a blurred full-frame background and the centered source band.
- **Depends on:** T10
- **Acceptance (sketch):** WHEN reframing, ffprobe SHALL report 1080×1920 output. **Re-plan after gate.**
- **Status:** todo (sketch)

### T12 — Burned phrase-level captions _(sketch)_
- **Goal:** Build styled phrase-level subtitles from segment timestamps and burn them in.
- **Depends on:** T11
- **Acceptance (sketch):** WHEN captioning, the output SHALL contain burned text synced to segment times, ≤ 2 lines, within safe margins. **Re-plan after gate.**
- **Status:** todo (sketch)

### T13 — Background job runner + progress endpoints _(sketch)_
- **Goal:** In-process single worker (concurrency = 1) running the full pipeline, with status/progress polled by the UI.
- **Depends on:** T12
- **Acceptance (sketch):** WHEN a process job is enqueued, `GET /jobs/{id}` SHALL report stage + progress until done/error. **Re-plan after gate.**
- **Status:** todo (sketch)

### T14 — Review UI (list + video + approve/reject) _(sketch)_
- **Goal:** FastAPI + htmx review screen: clip list, HTML5 video, score/reason/copy, approve/reject with keyboard shortcuts, plus a "process this video" trigger.
- **Depends on:** T13
- **Acceptance (sketch):** WHEN the operator approves/rejects a clip, its status SHALL persist and the list SHALL update without a full reload. **Re-plan after gate.**
- **Status:** todo (sketch)

### T15 — Permission/Creator CRUD UI + auth-file upload _(sketch)_
- **Goal:** Minimal UI to manage creators/permissions and upload the authorization file; enforce the gate in the web flow.
- **Depends on:** T14
- **Acceptance (sketch):** WHEN a source is submitted for processing without an active permission, the UI SHALL block it. **Re-plan after gate.**
- **Status:** todo (sketch)

### T16 — Export approved clips + provenance _(sketch)_
- **Goal:** Export each approved clip to a structured folder with `metadata.json`, a provenance stamp (source/creator/permission/tool version/model), editable copy, and optional `.srt`.
- **Depends on:** T15
- **Acceptance (sketch):** WHEN an approved clip is exported, the folder SHALL contain the mp4, metadata with provenance, and copy. **Re-plan after gate.**
- **Status:** todo (sketch)
