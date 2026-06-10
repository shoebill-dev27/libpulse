# ADR-005: LLM-Optional Pipeline

**Status:** Accepted

## Context
The `analyze` step uses an LLM to turn release notes/changelogs into candidate
breaking-change entries and before/after snippets. The pipeline runs unattended
for years after the build window, on cheap models, via cron. We must decide how
hard a dependency the LLM is.

## Decision
The pipeline **must run without an API key** in verify-only mode. LLM generation
is **optional**. The model is **configurable via env** (`LIBPULSE_MODEL`), with a
**cheap model as the default** for the unattended loop.

## Rationale
- **Verify is the moat, not generate** — verification (ADR-002) is what makes the
  data valuable and is pure execution; it needs no LLM. The loop must keep
  re-verifying and serving the existing corpus even if generation is disabled,
  rate-limited, or the API key is absent/expired.
- **Resilience for unattended operation** — an API outage, billing lapse, or key
  rotation must not crash or stall the cycle. Verify-only mode degrades
  gracefully: no new candidates, but the corpus stays fresh-verified and served.
- **Cost control** — the loop runs forever on a budget. Defaulting to a cheap
  model (overridable via `LIBPULSE_MODEL`) keeps per-cycle cost near zero; the
  expensive model is reserved for the human-attended build window if needed.
- **Vendor flexibility** — env-configurable model avoids hard-coding one model
  id, easing migration as cheaper/better models appear.

## Consequences
- `analyze` checks for `ANTHROPIC_API_KEY`; if absent, it is skipped and the
  cycle proceeds (watch → verify → store → export → report).
- Two operating modes documented in OPERATIONS.md: full (with key) and
  verify-only (without key).
- Snippet provenance stays internal (our pipeline only), preserving the
  execution-security posture (RISKS.md) regardless of which model generated them.
