# 0. Record architecture decisions

- Status: accepted
- Date: 2026-06-22

## Context

We need to capture the *why* behind significant technical choices so future
contributors (and future us) don't re-litigate settled decisions or
accidentally undo them. The choices already made for this project live in
`docs/PROJECT_BRIEF.md`; ongoing decisions should be recorded as they happen.

## Decision

We use **Architecture Decision Records** (Michael Nygard's format). Each ADR is
a short, numbered, dated Markdown file in `docs/adr/` describing one decision:
its context, the decision, and its consequences. ADRs are immutable once
accepted — to change a decision, write a new ADR that supersedes the old one.

## Consequences

- A new ADR is written (via `/adr`) whenever a non-trivial technical choice is
  made or changed.
- The PROJECT_BRIEF lists the decisions that should become ADRs before
  substantial coding: cloud LLM detection behind a provider interface (ADR-001),
  FastAPI+htmx review UI (ADR-002), blurred-pad 9:16 reframing (ADR-003),
  enforced permission gate + provenance (ADR-004), and pipeline-as-library +
  thin web layer (ADR-005).
- This file (ADR-0000) documents the practice itself.
