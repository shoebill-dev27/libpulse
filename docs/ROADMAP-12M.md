# LibPulse — 12-Month Roadmap

Rough, demand-gated. Built during the high-capability-model window (M0, until
2026-06-21), then maintained unattended by cheap models + cron. Later phases are
**gated on usage signals**, not calendar.

## M0 — Window (build now)
- Verification **harness** (uv venvs, 4 verdict types, log-and-skip loop).
- Full pipeline: watch → analyze → verify → store → export.
- **Corpus seed** — PyPI top ~50, last 12 months, ≥1 real migration VERIFIED
  end-to-end.
- **MCP server** over stdio serving VERIFIED entries.
- Verify-only mode working without API key.

## M1-2 — Distribution + Hardening
- **HuggingFace dataset** export (reputation/discovery for humans).
- **Apify actor** — pay-per-event wrapper over the same data.
- **Freshness automation hardening** — daily cron stable, weekly auto-report,
  failure handling proven across many cycles unattended.

## M3-4 — Paid API (gated)
- **REST API with metering** — *only if* MCP/API usage signals real demand.
  Reuses the same store/serializers.
- If no usage signal: hold; keep free tier + dataset running.

## M5-6 — npm Ecosystem
- Add **npm** behind the watch + verify abstraction (Node execution path).
- Extend corpus + MCP/dataset to cover npm top packages.

## M7-12 — Expansion or Steady-State
- **JetBrains plugin decision gate** — build only if API shows sustained usage.
- **Dataset licensing optionality** — package corpus + harness as a licensable
  asset (the $0-revenue fallback).
- Otherwise **steady-state**: unattended loop runs, quarterly kill-reviews,
  no new surface unless demand appears.
