# PROJECT_BRIEF.md — AI Clipping Tool (v1)

> Status: **scoped, awaiting approval to scaffold.** Produced via a Grill scoping session on 2026-06-22. No code written yet.

---

## Section 1 — The basics

**Elevator pitch.** A local-first macOS tool that ingests one authorized creator's long-form video, transcribes it, uses Claude to find the highest-potential short-form moments, and renders review-ready 9:16 captioned clips with suggested titles/descriptions/hashtags — for a human operator to approve and export. No posting in v1.

**The actual problem.** Manually finding and cutting the few genuinely clip-worthy moments out of an hour of podcast/interview footage is slow and judgment-heavy. The bet is that an LLM reading the transcript can surface those moments well enough to be worth the operator's review time.

**Who the user is.** A single operator (you) running clips for **one specific creator who has explicitly authorized it** — not your own content, and not a fleet of creators. One person at the keyboard; one content owner whose consent is on file.

**Definition of success (the number).** From a ~1-hour source video, v1 produces **3–5 clips the operator would genuinely be willing to post.** That is the bar. Quantity beyond that is not the goal; postability is.

**The riskiest assumption v1 exists to test.** *That automated detection actually surfaces clip-worthy moments.* Everything else (crop, captions, export) is plumbing around this one bet. If detection is mediocre, v1 has failed regardless of how polished the output looks.

**Anti-goals (what this is NOT — see also Non-Goals below).** Not a SaaS. Not multi-creator. Not a posting/automation farm. Not a copyright-risk reposting tool for random celebrities/streamers. Not a place to gold-plate cropping or captions while detection is unproven.

**Constraints.** macOS, two machines with different roles: **build/dev on a MacBook Pro M5 Pro (24 GB)**, but the **production runtime target is an idle MacBook Air M1 (8 GB)** that will be the dedicated machine for actually running the tool. **The 8 GB M1 Air is the constraining target — defaults are sized for it, not the Pro.** Local-first: media and transcription stay on the machine; only the (public-bound) transcript text goes to a cloud LLM. Operator is comfortable with Python/FastAPI/ffmpeg/AI APIs. Start small; expand later. Single `ANTHROPIC_API_KEY` for detection.

---

## Section 2 — Requirements

### Functional (must-have, ranked)
1. **Detect & rank clip-worthy moments** from a timestamped transcript via Claude, returned as structured candidates (start/end/score/reason + suggested title/description/hashtags). *This is the product.*
2. **Ingest → audio → local transcription** of a long local video into segment-level timestamps.
3. **Render** each candidate: cut 20–60s, reframe to 9:16 (blurred-pad), burn phrase-level captions.
4. **Review & approve/reject** in a local UI with real video playback and a fast keyboard loop.
5. **Enforced permission gate + export with provenance** — refuse to process a source with no permission record on file; stamp source/creator/permission/tool-version into every export.

### Non-functional
- **Scale:** 1 operator, 1 creator, a handful of videos at a time. No RPS/throughput concerns. *Explicitly not designing for multi-tenant scale.*
- **Latency:** processing a 1-hour video is a multi-minute job → must run as a non-blocking background job with progress. Detection API call is seconds (network). Transcription is the long pole and the main RAM consumer — **sized for the 8 GB M1 Air**: faster-whisper runs CPU-only on Mac, so default to a `small` int8 model on the Air (~5–12 min for an hour, ~1–1.5 GB RAM) and run pipeline stages **sequentially (worker concurrency = 1)** so Whisper and ffmpeg don't contend for the 8 GB. The M5 Pro can run a larger model and is only dev headroom.
- **Security:** localhost only (bind `127.0.0.1`); no auth in v1; secrets via `.env` (never committed). Permission + provenance records are the compliance surface.
- **Availability / i18n / a11y:** not applicable to a single-user local tool in v1. Stated explicitly so we don't build for them.
- **Cost:** ~$0.05–$0.50 per 1-hour video for detection (see Architecture → Model & cost). Negligible at personal scale.

### Future (6–12 months) — accommodated without rewrite
- Social publishers (YouTube Shorts / TikTok / Reels / X), OAuth account linking, analytics, learn-from-performance, multi-creator dashboard, agency/revenue workflows, watermark/branding, word-level karaoke captions, face-tracking reframe. The architecture reserves a `publishers/` boundary and a provider interface, but **none of these ship in v1.**

---

## Section 3 — Architecture

### Tech stack (rationale tied to a requirement)
- **Python 3.11+** — the ecosystem for faster-whisper, ffmpeg orchestration, and the Anthropic SDK lives here.
- **Pipeline as a standalone library + CLI** — the core flow is importable and runnable headless; the web app is a thin layer on top. Keeps the validation thesis testable without a UI and makes a future frontend swap cheap.
- **FastAPI + Jinja + htmx (server-rendered)** — the review loop needs a real HTML5 `<video>` for precise seeking and a snappy approve/reject keyboard loop, which directly affects how well you can judge "postable." Gives a real API that future publishers/dashboard reuse, with no SPA build. Chosen over Streamlit (rerun-on-click is clunky for a multi-clip review loop) and Next.js (overkill for single-user v1).
- **SQLite via SQLModel/SQLAlchemy** — single-user local; we need relational integrity across creator → permission → source → clip; trivial ops, no server.
- **ffmpeg / ffprobe via a subprocess arg-array wrapper** — industry-standard media processing; arg arrays (never shell strings) avoid injection and handle the space in the project path safely.
- **faster-whisper (local), behind a `Transcriber` protocol** — free, private, offline; emits word + segment timestamps. Runs CPU-only on Mac (CTranslate2 has no Metal backend), so model size is the speed/RAM lever: **default `small` int8 on the 8 GB M1 Air**, `medium`/`large-v3` allowed on the 24 GB M5 Pro — set per machine via config. The transcript only needs to be good enough for Claude to locate moments and for captions, so `small` is an acceptable accuracy floor. If accuracy on the Air disappoints, **`whisper.cpp` (CoreML/Metal-accelerated) is the drop-in escape hatch** — it runs `medium`/`large-v3` on the M1's GPU/ANE far faster than faster-whisper's CPU path. The protocol keeps the engine swappable, mirroring the `Detector` seam.
- **Anthropic Claude behind a `Detector` protocol** — best judgment for the core bet. Default **`claude-opus-4-8`**; **`claude-sonnet-4-6`** is a one-line cost fallback behind the same interface; a local LLM can be dropped in later. Uses **structured outputs** (clean JSON → DB), **adaptive thinking**, and the **1M context window** (no transcript chunking, even multi-hour).
- **In-process background worker (single worker, concurrency = 1) + jobs table + UI polling** — non-blocking processing without the weight of Celery/Redis. Concurrency = 1 is deliberate: on the 8 GB Air, Whisper and heavy ffmpeg must not run simultaneously. The heavy *intelligence* is a cloud call (near-zero local RAM), so the local machine only ever does media + transcription — which is exactly why this fits on 8 GB at all. Revisit only if the runtime machine grows.

### Model & cost (detection)
- Transcript sent to the LLM is **segment-level** ("[mm:ss] text…"), ~25–35K input tokens for 1 hour. Word-level timestamps stay local for caption rendering.
- One detection+copy pass ≈ ~4K output tokens. Per-video cost: **Opus 4.8 ≈ $0.25**, Sonnet 4.6 ≈ $0.15, Haiku 4.5 ≈ $0.05 (Haiku not recommended — too weak for nuanced clip judgment).
- **No chunking** needed (1M context). Verify exact token counts with `client.messages.count_tokens` on real transcripts (don't estimate with tiktoken).
- **Prompt caching** (cache the transcript prefix) cuts re-run input cost ~10× but only within the cache TTL — useful for back-to-back prompt-tuning, not for process-then-review-hours-later. Deferred as a v1.1 optimization; cost is already pennies.

### System architecture (data flow)
```
local video ─▶ ingest/probe ─▶ extract audio ─▶ faster-whisper ─▶ transcript(JSON, segment ts)
                                                                       │
                                          [Claude Detector, structured output] ◀┘
                                                       │
                                            candidate clips (start/end/score/reason/title/desc/hashtags)
                                                       │
                          per candidate: cut ─▶ reframe 9:16 (blurred-pad) ─▶ burn captions ─▶ clip.mp4
                                                       │
                                              Clip rows (status=pending)
                                                       │
                              operator review UI (FastAPI+htmx) ─▶ approve/reject
                                                       │
                              export: folder + metadata.json + provenance + (srt)
```
Permission gate sits in front of *ingest*: no valid permission record → processing refused.

### Data model (top entities)
1. **Creator** — id, name, handles/channels, notes.
2. **PermissionRecord** — id, creator_id, scope (platforms/channels covered), granted_at, `authorization_file_path` (uploaded email/PDF), status. *A Source cannot be processed without a valid one.*
3. **Source** — id, creator_id, permission_id, file_path, checksum, duration, resolution, transcript_path, created_at.
4. **Job** — id, source_id, type, status (queued/running/done/error), stage, progress, error, timestamps.
5. **Clip** — id, source_id, start, end, status (pending/approved/rejected), score, reason, title, description, hashtags, transcript_excerpt, output_path, provenance fields.

### API surface (internal, v1)
- `POST /sources` (register + permission check), `POST /sources/{id}/process` (enqueue job), `GET /jobs/{id}` (progress poll), `GET /clips?source=…`, `POST /clips/{id}/approve|reject`, `POST /clips/{id}/export`, `GET /media/{clip}` (serve mp4). Same surface a future publisher/dashboard builds on.

### Auth & hosting
- **Auth:** none in v1; single local operator; bind to `127.0.0.1` only. (Real auth is a SaaS-era concern.)
- **Hosting:** runs locally on the operator's Mac. Filesystem storage under a gitignored `storage/` (sources, work dirs per job, transcripts, outputs).

### ffmpeg safety wrapper
- Single module builds **argument lists** (no `shell=True`, no string interpolation), validates input paths exist, runs with timeouts, checks return codes, captures stderr tails for error reporting. `ffprobe` for duration/resolution/aspect. Reframe is a `filter_complex` blurred-pad to 1080×1920; captions burned via styled subtitles. Presence of `ffmpeg` checked at startup with a clear install hint.

### Future publishers (plug-in point, not built)
- `publishers/` package with a `Publisher` protocol (`publish(clip, account) -> result`). v1 ships only a `LocalExportPublisher` (writes the export bundle). OAuth/account linking, platform APIs, and posting-cadence safety are deferred behind this seam.

---

## Section 4 — SDLC plan

- **Repo:** single repo (monorepo unnecessary at this size). `src/clipper/` package + `tests/` + `docs/`.
- **Branching:** short-lived feature branches off `main`; commit per logical unit; never commit secrets or `storage/`.
- **Testing strategy:**
  - *Unit (where coverage matters):* timestamp math (20–60s clamping, segment-boundary snapping, padding), caption phrase-chunking (max chars/line, timing), filename/slug + metadata/provenance assembly, **permission-gate enforcement** (refuses without record), **Detector response parsing** (structured output → Clip objects), config loading.
  - *Integration/smoke:* full pipeline on a tiny fixture video with a **deterministic mock Detector** (free, repeatable) → produces N clips, 9:16, captioned, exportable.
  - *ffmpeg outputs:* assert via ffprobe (dimensions = 1080×1920, duration within tolerance, file plays) — **never** assert exact bytes.
  - *Honestly untested:* real LLM judgment quality (non-deterministic — validated by manual eyeball, not asserted) and exact transcription accuracy.
- **CI:** lint + type-check + unit + mock-Detector integration on push. (ffmpeg installed in CI image.)
- **Observability:** structured logging per job stage; job rows carry stage + error; ffmpeg stderr tail captured on failure. No external telemetry in v1.
- **Docs:** this brief + ADRs in `docs/adr/`; README with macOS setup (Homebrew ffmpeg, model download, `.env`).
- **Release:** local tool; tagged versions; `tool_version` stamped into exports for provenance.

### Verification plan
- **Sample video:** for real evaluation, one of the authorized creator's existing long videos. For dev/CI, a tiny self-recorded or CC-licensed ~60–90s fixture committed under `tests/fixtures/`.
- **Manual QA checklist:** process a real ~1-hour authorized video → confirm 3–5 candidates surface; for each clip eyeball: aspect ratio 9:16, captions readable + synced + no overflow, cut boundaries not mid-word, audio in sync, suggested copy sane, provenance/metadata correct; confirm a source with **no permission record is refused**; confirm export folder structure.
- **Quality gate at Phase 2** (detection) *before* building render: eyeball candidate quality on a real transcript. If it's not surfacing genuinely good moments, stop and iterate the prompt — do not proceed to polish.

---

## Section 5 — Risks & open questions

### Top risks
1. **[Product/Technical] Detection quality is insufficient** — the core bet fails. *Mitigation:* invest in the detection prompt; use Opus 4.8; gate at Phase 2 with manual eval before building downstream; iterate against a few hand-labeled examples; keep the provider swappable.
2. **[Operational/Legal] Account safety even with permission** — platforms throttle/ban for reposted-duplicate detection, licensed background music, watermark detection, or botted cadence, *independent of* creator consent. *Mitigation:* v1 does not post; permission record + provenance prove good faith; write a platform-compliance checklist before any publisher is built; human approval gate stays.
3. **[Technical] Build-on-Pro / run-on-Air drift + macOS env fragility** — dev happens on a fast 24 GB M5 Pro but the tool must actually run on an idle 8 GB M1 Air, so RAM pressure and CPU-transcription speed can pass on the Pro and fail on the Air; plus ffmpeg-missing and model-download-size issues. *Mitigation:* size all defaults for the 8 GB Air (`small` Whisper, worker concurrency = 1); **validate a real 1-hour run on the Air before calling v1 done**; startup ffmpeg check with install hint; configurable model size; `whisper.cpp` Metal escape hatch; async job + progress so slowness isn't a hang.

### Risk checklist (build-time)
- [ ] Clip boundaries snap to segment edges + small pad (no mid-word cuts).
- [ ] Caption phrase-chunking has max chars/line and tested timing (no overflow/desync).
- [ ] All paths handled space-safely (project dir is `clipping tool`); ffmpeg via arg arrays only.
- [ ] Secrets in `.env`; `.env`, `storage/`, model caches in `.gitignore`.
- [ ] Never overwrite the source; per-job work dirs; cleanup on success.
- [ ] Tests use the mock Detector (deterministic, free) — no live API in CI.
- [ ] Permission gate enforced at the processing entrypoint (not just UI).
- [ ] `max_tokens` capped; structured-output schema validated; handle `stop_reason == "refusal"`.
- [ ] Performance validated on the 8 GB M1 Air (not just the Pro): a real 1-hour run fits in RAM and completes; Whisper defaulted to `small` and worker concurrency = 1 on the Air.

### Open questions / deferred decisions
- **Mac hardware specs** — ✅ *resolved (2026-06-22):* build on MacBook Pro M5 Pro (24 GB); **runtime target is the idle MacBook Air M1 (8 GB).** Decision: default Whisper `small` int8 + worker concurrency = 1 on the Air; `medium`/`large-v3` permitted on the Pro for dev; model size configurable per machine; `whisper.cpp` reserved as the Metal escape hatch.
- **Creator second-approval gate** — deferred. *Trigger: when >1 creator or moving toward agency.*
- **Word-level karaoke captions** — deferred to v1.1. *Trigger: after detection is proven.*
- **Prompt-caching TTL strategy** — deferred. *Trigger: when re-run cost actually matters.*
- **Which platform to publish to first** — deferred to v2. *Trigger: after clip quality validated AND account-safety policy written.*

### ADRs to write before code
- ADR-001 — Cloud LLM (Claude) for detection behind a provider interface (vs local LLM).
- ADR-002 — FastAPI + htmx review UI (vs Streamlit / Next.js).
- ADR-003 — Blurred-pad 9:16 reframing (vs face-tracking) for v1.
- ADR-004 — Enforced permission gate + provenance metadata (account-safety posture).
- ADR-005 — Pipeline-as-library + thin web layer (architecture boundary).

---

## Section 6 — Roadmap

### v1 scope (in)
Single-operator local tool that, for **one authorized creator**, takes a long local video → transcribes locally → Claude detects/ranks 3–5 postable moments with suggested copy → renders 9:16 blurred-pad clips with burned phrase captions → operator approves/rejects in a local web UI → exports approved clips with metadata + provenance. Processing is **refused without a permission record on file.**

### Non-goals (explicitly out of v1)
- ❌ Posting/publishing to any platform (architecture-ready only)
- ❌ OAuth / account linking
- ❌ Multi-creator or any multi-tenancy
- ❌ Analytics / learn-from-performance
- ❌ Auto-approval (human gate is mandatory)
- ❌ Face-tracking reframe, word-level karaoke captions
- ❌ Billing / agency / revenue workflows, watermark/branding
- ❌ Auth, cloud hosting, remote access

### Implementation phases (each leaves the app runnable; acceptance criteria stated)
- **Phase 0 — Scaffold & contracts.** Repo skeleton, `config`, DB schema + entities (incl. PermissionRecord), ffmpeg/ffprobe wrapper, CLI stub, **mock Detector**, test harness, CI. *Acceptance:* `clipper --help` runs; DB initializes; tests green; ffmpeg presence checked.
- **Phase 1 — Ingest + transcribe + permission gate.** Register a source under a creator+permission (enforced); probe; extract audio; faster-whisper → stored segment-timestamped transcript. *Acceptance:* `clipper ingest <file>` (with a permission record) yields a stored transcript on a short fixture; ingest **refused** without a record.
- **Phase 2 — Detection (the core bet).** `Detector` protocol + Claude provider (Opus 4.8, structured outputs, adaptive thinking); transcript → ranked candidate clips (clamped 20–60s, snapped to segment boundaries) with title/description/hashtags; persist Clip rows. *Acceptance:* on a real transcript, returns structured ranked candidates; mock provider in tests; **manual eyeball gate** on candidate quality before proceeding.
- **Phase 3 — Render.** Cut + blurred-pad 9:16 + burned phrase captions per candidate. *Acceptance:* each candidate yields a playable 1080×1920 mp4 with readable synced captions; ffprobe assertions pass.
- **Phase 4 — Review UI + jobs.** FastAPI + htmx: list clips, HTML5 video, show score/reason/copy, approve/reject + keyboard shortcuts; "process this video" as a background job with progress polling. *Acceptance:* operator runs a video end-to-end in the UI, watches progress, reviews and approves/rejects; states persist.
- **Phase 5 — Permission UI + export + provenance.** Minimal Creator/PermissionRecord CRUD + authorization-file upload; export approved clips to structured folders with metadata, provenance stamp, and editable copy. *Acceptance:* processing blocked without permission via UI too; approved clips export with full metadata + provenance.
- **Phase 6+ (post-v1, deferred):** publishers, OAuth, analytics, multi-creator — behind the reserved seams; not started until v1 proves clip quality.

### First-sprint task list (concrete, ordered)
1. Write ADR-001…005.
2. Set Whisper defaults per machine (`small` on the Air, larger on the Pro) per the resolved specs.
3. Scaffold repo (Phase 0): package, config, DB models, ffmpeg wrapper, CLI, mock Detector, CI.
4. Phase 1: ingest + permission gate + faster-whisper transcript on a fixture.
5. Phase 2: Claude Detector + structured candidate schema → eyeball-eval on a real transcript (**go/no-go gate**).

### Proposed file structure
```
clipping-tool/
  pyproject.toml   README.md   .env.example   .gitignore   CLAUDE.md
  docs/ (PROJECT_BRIEF.md, adr/)
  src/clipper/
    config.py   cli.py
    db/        (models.py, session.py)
    media/     (ffmpeg.py, probe.py, audio.py, cut.py, reframe.py, captions.py)
    transcribe/(base.py [Transcriber protocol], whisper_local.py)
    detect/    (base.py [protocol+schema], claude.py, mock.py)   # copy-gen lives in the same call
    pipeline/  (jobs.py, stages.py)
    permissions/(service.py)        # gate enforcement
    export/    (exporter.py)        # folder + metadata + provenance
    publishers/(base.py, local_export.py)   # future seam; v1 = local only
    web/       (app.py, routes.py, templates/, static/)
  tests/ (unit/, integration/, fixtures/sample_60s.mp4)
  storage/   # gitignored: sources, work, transcripts, outputs
```

### Monetization / product direction
v1 is an **internal validation tool**, not a product. It exists to answer one question: *can this reliably produce 3–5 postable clips per hour of authorized source?* Metrics that matter: **postable-clip yield per source-hour** and **operator minutes per approved clip**. Do not build SaaS, billing, multi-tenant, analytics, or publishers until that question is answered yes.
