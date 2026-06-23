# QA — detection (Phase 2)

Two reviewers on the same baseline (`feat/detection` HEAD `50dd258`, diff vs `main`):
the **Verifier subagent** (same-model, isolated) and **Codex** (cross-model). Verdicts
differ on severity of the postprocess issues — both are being fixed before ship.

---

## Verifier subagent — verdict: SHIP

### Blockers
- None. Matches design.md, conforms to ADR-0001, respects anti-goals. Gates green (ruff, mypy 34 files, 137 tests with `ANTHROPIC_API_KEY` unset + no network). Clients injected in tests; unset-key → `DetectorConfigError`; temperature correctly omitted for `claude-opus-4-8`.

### Non-blocking issues
- **Inverted model times (start>end) become a fabricated 20s clip instead of being dropped** (postprocess.py clamp-before-drop). temperature=0 + schema text make it unlikely. Fix: drop where raw pre-clamp end<=start, or a model_validator.
- dedup_overlapping greedy replacement can leave a stale conflict on 3-way overlaps (order-sensitive). Disclosed; ranking still applies.
- config.py detector_fallback_model unused (dead config).
- openai_compat brace-span JSON extraction fragile (dev-only path, low-risk).

### Coverage gaps
- inverted start>end through postprocess; excerpt_for when clip extended past segment text; CLI `--provider claude` no-key → exit 1; UnknownProviderError → CLI exit 1.

### Verdict: SHIP

---

## Codex — verdict: NO_SHIP

### Blockers
- `postprocess.py:173/176/179`: invalid zero-length or reversed candidates can be repaired into valid clips instead of dropped — `start==end==30` or `start=90,end=30` is passed to `clamp_duration`, which extends `end` to `start+20` before the `end<=start` drop. Violates "drop invalid".
- `postprocess.py:134/136-145`: dedup not globally enforcing ">50% overlap keeps higher score." A candidate overlapping multiple kept clips only compares against the first conflict, so it can replace a lower-scored keeper while remaining >50% overlapped with a later higher-scored keeper → near-duplicates.

### Non-blocking issues
- `openai_compat.py:141` sets `response_format.json_schema.strict=True`, but the shared schema (`prompt.py:34`) omits strict constraints (`additionalProperties:false`, optional fields not in `required`). Fine for Ollama; weaker for a strict keyed cloud endpoint.
- `service.py:157` persists detector times as-is, not clamped/checked against `Source.duration_seconds` (providers use transcript-max as duration — usually fine, but the persistence invariant isn't enforced).
- Handoff is honest; the outstanding real Claude/Air go-no-go is clearly called out.

### Suggested tests
- postprocess: raw `start==end`, raw `end<start`, become-`end<=start`-after-snap → expect drop, not extension.
- 3-way dedup: new candidate overlaps two kept clips → must not survive if it conflicts with a higher-scored keeper.
- service: `Source.duration_seconds` shorter than candidate end → persisted rows clamped or refused.
- OpenAI-compatible strict-schema request-shape variant.

### Verdict: NO_SHIP

### Reasoning
Provider plumbing, CLI, eval, and tests are broadly aligned with the design and pass without network/key. But the pure postprocess is the shared correctness boundary for both providers and violates two core contracts: invalid ranges can become clips, and dedup can return >50%-overlapping candidates.

---

## Consolidated verdict + action (autonomous fix pass)

Both reviewers flag the **postprocess correctness** issues; Codex (correctly) rates them ship-blocking. Per the session's autonomous mandate, fixing before ship — NOT shipping over known blockers:

- **B1 — drop invalid ranges:** in `postprocess`, drop any candidate whose times are degenerate/inverted (`end <= start`) BEFORE `clamp_duration` can extend them. + tests (raw start==end, raw end<start, degenerate-after-snap).
- **B2 — globally-correct dedup:** rewrite `dedup_overlapping` to sort by (score desc, duration desc, start asc) then greedily keep a candidate only if it overlaps NO already-kept clip by >50%. Guarantees the highest-scored of any overlapping group survives and no >50% pair remains. + 3-way test.
- **N1 — enforce persistence invariant:** `service` clamps persisted clip times to `[0, Source.duration_seconds]` and drops any that go degenerate. + test (duration shorter than candidate end).
- Accepted/deferred: `detector_fallback_model` dead config (pre-existing scaffold — left, noted); openai_compat `strict`+brace-span (dev-only Ollama path, proven working — noted; cloud-strict-schema is a later concern).

Re-gate after fixes, then re-run Codex for a SHIP verdict before opening the PR.

---

## Re-QA after fixes (autonomous loop)

- **Fix `1a0a438`** (drop-invalid + globally-correct dedup + service duration-clamp) → **Codex round-2:** dedup blocker RESOLVED; flagged the invalid-range fix as only *partial* — snapping widens times outward, so a raw zero-length `(50,50)` / reversed `(60,50)` could still snap to `(0,100)` and survive. **NO_SHIP.**
- **Fix `8006f7b`** (drop raw `end<=start` BEFORE snapping; + mid-segment regression tests) → **Codex round-3: SHIP.** Both prior blockers confirmed resolved; Codex ran `pytest -q` → 146 passed. Only non-blocking nits left (stale doc pipeline-order references), fixed in the same pass.

**Final QA state: Verifier SHIP + Codex SHIP. Gate green (146 tests). Approved for ship.**
Outstanding: **T6** — the human go/no-go gate on a real Opus run over an Air-ingested ~1-hr transcript (blocks Phase 3, not this code).
