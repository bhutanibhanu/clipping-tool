# AGENTS.md

This project keeps one set of working rules for all coding agents. The full
guidance lives in [`CLAUDE.md`](CLAUDE.md) — read it. The essentials:

- **Project:** `clipper` — local-first macOS tool, one authorized creator's
  long-form video → 9:16 captioned short-form clips. No posting in v1. The bet
  is detection quality. Scope: `docs/PROJECT_BRIEF.md`.
- **Stack:** Python 3.11+ (`uv`, dev venv 3.13), SQLAlchemy 2.0 + SQLite,
  FastAPI + htmx, typer CLI, ffmpeg via arg-array wrapper, faster-whisper +
  Claude (`claude-opus-4-8`) behind `Transcriber` / `Detector` protocols.
- **Setup / checks:**
  ```sh
  uv venv --python 3.13 && uv pip install -e ".[dev]"
  .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest
  ```
- **Runtime constraint:** production target is an idle 8 GB M1 Air, not the
  build Pro — default Whisper `small`, worker concurrency = 1; validate a real
  1-hour run on the Air before declaring a phase done.
- **Never commit** secrets, `.env`, `storage/`, or `*.db`. Tests use the
  MockDetector (no live API). New decisions → an ADR in `docs/adr/`.
- **Anti-goals (v1):** no posting, OAuth, multi-creator, analytics, billing,
  face-tracking, word-level captions.
