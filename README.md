# clipper

Local-first AI clipping tool for macOS. It turns **one authorized creator's**
long-form video into review-ready **9:16 captioned short-form clips** — transcribe
locally, let Claude find the high-potential moments, render vertical captioned
clips, and approve/export them by hand. **No social posting in v1.**

> **Status: Phase 0 skeleton.** Contracts, config, DB schema, and a runnable
> CLI + web health check are in place. The pipeline (ingest → transcribe →
> detect → render → review → export) is built in Phases 1–5. Full scope,
> decisions, and roadmap live in [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md).

## Requirements

- **Python 3.11+** (the project pins its dev venv to 3.13).
- **[uv](https://docs.astral.sh/uv/)** for env + dependency management.
- **ffmpeg** — required for media processing in Phase 1+ (`brew install ffmpeg`).
  Not needed for the Phase 0 skeleton.
- **An Anthropic API key** in `ANTHROPIC_API_KEY` — required for detection in Phase 2+.

This runs on Apple Silicon. **The runtime target is an idle 8 GB MacBook Air M1**,
so defaults (`small` Whisper model, single sequential worker) are sized for it;
the 24 GB M5 Pro used for development can run larger models — override via `.env`.

## Setup

```sh
uv venv --python 3.13
uv pip install -e ".[dev]"
cp .env.example .env   # then add your ANTHROPIC_API_KEY (only needed from Phase 2)
```

## Run

```sh
.venv/bin/clipper --help
.venv/bin/clipper doctor          # environment + config readiness check
.venv/bin/uvicorn clipper.web.app:app --host 127.0.0.1 --port 8000
#   → http://127.0.0.1:8000/health
```

## Test / lint / type-check

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
.venv/bin/pytest
```

## Layout

```
src/clipper/
  config.py        runtime settings (sized for the 8 GB Air)
  cli.py           `clipper` CLI (version, doctor)
  db/              SQLAlchemy 2.0 models + engine (Creator→Permission→Source→Job/Clip)
  media/           safe ffmpeg/ffprobe wrapper (stage filters land in Phase 3)
  transcribe/      Transcriber protocol (faster-whisper engine: Phase 1)
  detect/          Detector protocol + CandidateClip schema + MockDetector (Claude: Phase 2)
  web/             FastAPI + htmx review UI (review/approve: Phase 4)
  pipeline/        job orchestration (Phases 1–4)
  permissions/     enforced consent gate (Phase 1/5)
  export/          export + provenance (Phase 5)
  publishers/      reserved seam — no posting in v1
tests/             unit + smoke tests (mock detector, no live API)
docs/              PROJECT_BRIEF.md + ADRs
```

## License

Proprietary — all rights reserved. See [LICENSE](LICENSE).
