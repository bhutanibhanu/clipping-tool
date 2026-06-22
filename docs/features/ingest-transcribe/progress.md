# Progress: ingest-transcribe (v1 Phase 1)

_Sliced 2026-06-22 from `docs/features/v1/progress.md` (T1–T5) · 5 tasks + T6 (added from QA) · supervised build_

Design: [`design.md`](./design.md). Master plan: [`docs/features/v1/progress.md`](../v1/progress.md).
CLI shape: registration (`source add`, where the gate fires) is split from
processing (`ingest <source_id>`).

## Task list
- [x] T1 — Consent records: `creator add` + `permission grant` (a45bb3b)
- [x] T2 — Permission-gated `source add` (02c88b0)
- [x] T3 — ffprobe probe + audio extraction (77f986c)
- [x] T4 — faster-whisper transcriber + transcript persistence (10f38b2)
- [x] T5 — `clipper ingest <source_id>` pipeline wiring (e41a139)
- [x] T6 — Fix: creator-existence check + FK enforcement (QA blocker) + cleanups (bef9185)

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
- **Status:** done (a45bb3b)

### T2 — Permission-gated `source add`
- **Goal:** Register a local video as a Source only if its creator has an active permission; refuse otherwise.
- **Depends on:** T1
- **Files (expected):** `src/clipper/permissions/service.py` (`require_permission` gate), `src/clipper/catalog.py` (`register_source`), `src/clipper/cli.py`, `tests/test_sources.py`
- **Acceptance:**
  - WHEN `clipper source add --file <v> --creator <id>` runs and the creator has an active PermissionRecord, the system SHALL create a Source row linked to that permission and print its id.
  - WHEN the creator has no active PermissionRecord, the system SHALL raise `PermissionRequiredError`, exit non-zero, and create no Source row.
  - WHEN `<file>` does not exist, the system SHALL exit non-zero and create no Source row.
- **Tests:** gated allow (active) / refuse (none, revoked); missing file refused; created Source references the correct permission_id.
- **Status:** done (02c88b0)

### T3 — ffprobe probe + audio extraction
- **Goal:** Probe duration/resolution and extract a 16 kHz mono WAV for transcription, on top of the Phase 0 ffmpeg wrapper.
- **Depends on:** none
- **Files (expected):** `src/clipper/media/probe.py`, `src/clipper/media/audio.py`, `tests/test_probe.py`, `tests/conftest.py` (synthetic-clip fixture)
- **Acceptance:**
  - WHEN `probe(path)` parses ffprobe JSON, the system SHALL return duration (seconds, float), width, and height.
  - WHEN `extract_audio(src, dst)` runs, the system SHALL produce a 16 kHz mono WAV at `dst` via an argument-list ffmpeg call (no shell string).
  - WHEN ffmpeg/ffprobe is absent, both SHALL raise `FFmpegNotFoundError`.
- **Tests:** unit — `probe` field-mapping from a captured ffprobe JSON string (no ffmpeg needed). Integration — generate a ~10 s `lavfi` test clip, probe + extract, assert WAV exists with expected sample rate; `@pytest.mark.integration`, skipped when ffmpeg is unavailable.
- **Status:** done (77f986c)

### T4 — faster-whisper transcriber + transcript persistence
- **Goal:** Implement the `Transcriber` protocol with faster-whisper (model/compute from config, `small`/`int8` default) and persist the transcript as JSON, setting `Source.transcript_path`.
- **Depends on:** T3
- **Files (expected):** `src/clipper/transcribe/whisper_local.py`, `src/clipper/transcribe/store.py` (Transcript ⇄ JSON), `tests/test_transcribe_store.py`. Installs the `[transcribe]` extra.
- **Acceptance:**
  - WHEN `WhisperTranscriber().transcribe(audio_path)` runs, the system SHALL return a `Transcript` whose segments each satisfy `start <= end` and non-empty text.
  - WHEN the transcript is saved, the system SHALL write JSON under `storage/` and set `Source.transcript_path`.
  - The model size and compute type SHALL be read from `Settings` (default `small` / `int8`).
- **Tests:** unit — `Transcript`⇄JSON round-trip (no model). Integration — transcribe the synthetic fixture's audio, assert ≥1 segment; `@pytest.mark.integration`, skipped when `faster-whisper`/ffmpeg are unavailable.
- **Status:** done (10f38b2)

### T5 — `clipper ingest <source_id>` pipeline wiring
- **Goal:** Run probe → extract audio → transcribe sequentially as a Job (concurrency = 1), recording stage/progress and capturing stage errors; re-check the permission gate at ingest time.
- **Depends on:** T2, T3, T4
- **Files (expected):** `src/clipper/pipeline/stages.py`, `src/clipper/pipeline/jobs.py`, `src/clipper/cli.py`, `tests/test_pipeline_ingest.py`
- **Acceptance:**
  - WHEN `clipper ingest <source_id>` runs on a permitted source, the system SHALL create a Job, run the three stages in order, set `Job.status=done`, and populate `Source.duration_seconds`, width/height, and `transcript_path`.
  - WHEN the source's permission is missing or revoked at ingest time, the system SHALL refuse and leave no Job in `done`.
  - WHEN a stage raises, the system SHALL set `Job.status=error` with the failing `stage` recorded, and the process SHALL NOT crash.
- **Tests:** unit — stage runner with a mock transcriber + monkeypatched media functions asserts stage order, progress/status transitions, and error capture. Integration — end-to-end on the fixture; skipped without ffmpeg/whisper.
- **Status:** done (e41a139)

### T6 — Fix: creator-existence check + FK enforcement (QA blocker) + cleanups
- **Goal:** Close the orphan-permission hole both QA reviewers flagged (Codex rated it a blocker), and fold in two cheap robustness fixes they noted.
- **Depends on:** T1–T5
- **Files (expected):** `src/clipper/permissions/service.py`, `src/clipper/catalog.py`, `src/clipper/db/session.py`, `src/clipper/transcribe/whisper_local.py`, `src/clipper/cli.py`, `tests/test_permissions.py`, `tests/test_sources.py`, `tests/test_transcribe_store.py`
- **Acceptance:**
  - WHEN `grant_permission` / `clipper permission grant` is given a creator id with no Creator row, the system raises a clear error (e.g. `CreatorNotFoundError`) / exits non-zero and persists NO PermissionRecord.
  - WHEN an app engine is created, SQLite foreign-key enforcement is ON (`PRAGMA foreign_keys=ON`), so orphan `creator_id`/`permission_id` rows are rejected at the DB layer.
  - WHEN `source add` / `require_permission` is used with a nonexistent creator, no Source is registered (the gate holds even if an orphan permission row somehow existed).
  - WHEN a transcript is produced, segments whose text is empty/whitespace-only are dropped (design says segments have non-empty text).
  - WHEN `faster-whisper` is not installed, `clipper ingest` exits 1 with a clear message (no raw traceback).
- **Tests:** grant with unknown creator → error + zero PermissionRecords; FK pragma enabled (`PRAGMA foreign_keys` == 1, and an orphan FK insert raises `IntegrityError`); empty-segment filtering drops blanks; `source add` refused for unknown creator.
- **Status:** done (bef9185)
