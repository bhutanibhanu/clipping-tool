# CLAUDE.md — working rules for this repo

## What this is

`clipper` is a local-first macOS tool that turns **one authorized creator's**
long-form video into review-ready 9:16 captioned short-form clips: transcribe
locally → Claude detects high-potential moments → render vertical captioned
clips → operator approves → export with provenance. **v1 does not post to any
platform.** Full scope and decisions: `docs/PROJECT_BRIEF.md`.

The whole bet is **detection quality** — invest effort there; keep cropping,
captions, and export "good enough."

## Tech stack

- Python 3.11+ (dev venv pinned to 3.13), managed with `uv`.
- Pipeline-as-library + `typer` CLI; FastAPI + Jinja + htmx review UI.
- SQLAlchemy 2.0 + SQLite. pydantic v2 for config and the detector schema.
- ffmpeg/ffprobe via a subprocess **arg-array** wrapper (never shell strings).
- faster-whisper (local, CPU on Mac) behind a `Transcriber` protocol;
  Claude (`claude-opus-4-8`) behind a `Detector` protocol.

## Commands

```sh
uv venv --python 3.13 && uv pip install -e ".[dev]"
.venv/bin/clipper doctor
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest
```

## Repo layout

`src/clipper/{config,cli}.py`, `db/`, `media/`, `transcribe/`, `detect/`,
`web/`, `pipeline/`, `permissions/`, `export/`, `publishers/`; `tests/`;
`docs/` (brief + ADRs). One package, `src/` layout.

## Conventions

- Short-lived feature branches off `main`; small, logical commits.
- **Never commit** secrets, `.env`, `storage/`, or `*.db`.
- All paths handled space-safely (the working dir is literally `clipping tool`);
  ffmpeg is always invoked with an argument list, never an interpolated string.
- Tests use the **MockDetector** — no live API calls, no key needed in CI.
- New architecture decisions get an ADR in `docs/adr/` (see `/adr`).

## The runtime constraint (important)

The production target is an **idle 8 GB MacBook Air M1**, not the 24 GB M5 Pro
used to build. Size everything for the Air: default Whisper `small`, worker
**concurrency = 1** (Whisper and ffmpeg must not run at once). Detection is a
cloud call (near-zero local RAM). **Validate a real 1-hour run on the Air before
calling any phase done.**

## Before opening a PR

1. `ruff check .` and `ruff format --check .` clean
2. `mypy` clean
3. `pytest` green
4. No secrets / `storage/` / `.env` staged

## Anti-goals (v1)

No posting/publishing, OAuth, multi-creator, analytics, billing, face-tracking,
or word-level captions. `publishers/` is a reserved seam only. Don't build ahead
of the detection-quality validation.
