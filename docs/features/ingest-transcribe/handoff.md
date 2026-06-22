# Feature Handoff: ingest-transcribe

## Goal
Take a local video belonging to one authorized creator and turn it into a stored,
timestamped transcript — gated so nothing is processed without a permission record
on file. (v1 Phase 1, tasks T1–T5.)

## Files changed
```
 docs/features/ingest-transcribe/design.md   |  48 ++++
 docs/features/ingest-transcribe/progress.md |  76 ++++++
 docs/features/ingest-transcribe/state.json  |   7 +
 pyproject.toml                              |   7 +
 src/clipper/catalog.py                      |  69 +++++
 src/clipper/cli.py                          | 114 ++++++++-
 src/clipper/db/session.py                   |  38 ++-
 src/clipper/media/audio.py                  |  37 +++
 src/clipper/media/probe.py                  |  59 +++++
 src/clipper/permissions/service.py          |  87 +++++++
 src/clipper/pipeline/jobs.py                |  94 +++++++
 src/clipper/pipeline/stages.py              |  86 +++++++
 src/clipper/transcribe/store.py             |  48 ++++
 src/clipper/transcribe/whisper_local.py     |  44 ++++
 tests/conftest.py                           |  56 ++++
 tests/test_catalog.py                       |  40 +++
 tests/test_cli_consent.py                   | 111 ++++++++
 tests/test_permissions.py                   | 123 +++++++++
 tests/test_pipeline_ingest.py               | 383 +++++++++++++++++++++
 tests/test_probe.py                         | 118 +++++++++
 tests/test_sources.py                       | 218 ++++++++++++++++
 tests/test_transcribe_store.py              |  62 +++++
 tests/test_whisper.py                       |  31 +++
 23 files changed, 1952 insertions(+), 4 deletions(-)
```

## How to run
```sh
# in the worktree, with the venv set up (uv venv --python 3.13 && uv pip install -e ".[dev,transcribe]")
.venv/bin/clipper creator add --name "Creator Name"
.venv/bin/clipper permission grant --creator 1 --scope youtube --auth-file ./signed-consent.pdf
.venv/bin/clipper source add --file ./long-video.mp4 --creator 1
.venv/bin/clipper ingest 1          # probe -> extract audio -> transcribe -> persist
# tests:
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest
```

## Expected behavior
- `creator add` / `permission grant` seed the consent record (auth file path recorded, not copied); missing auth file → exit 1, nothing persisted. `permission grant` also rejects an unknown creator id (exit 1, nothing persisted), and SQLite foreign-key enforcement is ON, so orphan permission/source rows are rejected at the DB layer (T6, post-QA fix).
- `source add` is **refused (exit 1, no row)** unless the creator has an active permission; also refused if the file is missing.
- `ingest <source_id>` runs probe → audio → transcribe → persist as a single sequential `Job` (concurrency = 1), populating `Source.duration_seconds/width/height/transcript_path` and writing `storage/transcripts/<id>.json`; on a stage error the Job is marked `error` with the failing stage and the process does not crash; the permission gate is re-checked before any Job is created.

## Test plan
- **59 tests, all green** (`ruff` + `mypy` 28 files + `pytest`) — includes T6's creator-validation + FK-enforcement tests. Mix of unit (services, gate, probe-parsing, transcript serialization, stage ordering/error capture — all in-memory, no ffmpeg/whisper) and `@pytest.mark.integration` tests that **actually ran** in this env: ffprobe/extract on a lavfi clip, faster-whisper `tiny` on a macOS `say` speech clip, and a full end-to-end ingest of a spoken clip (Job → done, transcript ≥1 segment).
- **Not yet covered:** a real ~1-hour video, and a run on the **8 GB M1 Air with the default `small` model** — that is the brief's mandated manual validation gate and has not been done.

## Known risks
- **`small` model on the 8 GB Air is unvalidated** — all whisper runs here used `tiny` on the 24 GB Pro. RAM/latency on the Air is the open question (per the brief). First place to look if ingest is slow/OOMs on the Air.
- **ffmpeg / faster-whisper must be present** for ingest; absence raises `FFmpegNotFoundError` / a clear RuntimeError. Integration tests skip cleanly when tools are missing (e.g. CI without `[transcribe]`/`say`).
- **No probe of media validity beyond ffprobe** — a corrupt/zero-byte file registered via `source add` (which only checks existence) would fail at the probe stage and be recorded as a Job error (by design).

## Open questions
- `SourceNotFoundError` currently lives in `pipeline/jobs.py`; could move next to `SourceFileNotFoundError` in `catalog.py` (cosmetic).
- Whisper model download (`tiny`/`small`) happens on first use and needs network; no pre-fetch/`doctor` check yet (fine for Phase 1).
- Async background worker + progress polling is deliberately deferred to T13 (Phase 4); `ingest` is synchronous for now.
