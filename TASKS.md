# TASKS — LibPulse

Granularity: each task is 1–3 hours for a Claude Code session. Dependencies noted.

## Done

- [x] T01 Repo scaffold, pyproject, gitignore, env example
- [x] T02 Core models (MigrationCase, Verdict, VerificationResult)
- [x] T03 Verifier: uv venv cache + isolated snippet runner + 3-proof verdict logic
- [x] T04 Store: SQLite + deterministic corpus JSON export (verified-only)
- [x] T05 CLI with crash-proof `cycle` (ingest → verify → export → report)
- [x] T06 Tests: 11 unit + 2 integration (real numpy 2.0 case VERIFIED end-to-end)
- [x] T07 Doc pack: PRD, MVP, ADR-001..005, RISKS, OPERATIONS, ROADMAP-12M
- [x] T08 Watcher: poll PyPI JSON API for tracked packages (packages.txt, curated 20),
      detect new final releases since last cycle, persist watermarks in store. No API keys.
- [x] T09 Analyzer: release notes context (PyPI metadata + GitHub releases public API),
      LLM-generated candidate cases → data/cases/ via Messages API (raw HTTP, stdlib).
      LIBPULSE_MODEL env (default claude-haiku-4-5); skips cleanly when no key.
- [x] T10 Wired watcher+analyzer into `cycle` (watch → analyze → ingest → verify →
      export → report); per-stage failures logged, never crash. `analyze` debug command.

## Next (MVP)
- [ ] T11 MCP server (stdio, official `mcp` SDK as optional extra): tools =
      query_migrations(package, from_version?, to_version?), list_packages().
      Serves data/corpus/. Depends: T04.
- [ ] T12 Seed corpus: curate top-50 package list; run loop over their releases from
      the last 12 months; triage verdicts. Depends: T10. (Bulk, parallelizable.)
- [ ] T13 Weekly markdown report generator (corpus growth, freshness lag, verdict
      mix) + cron/scheduled-agent setup for the post-window unattended cadence.
- [ ] T14 SECURITY_REVIEW.md (threat model: LLM-generated code execution, supply
      chain via pip installs of watched packages) — before any public publication.
- [ ] T15 HuggingFace dataset export format + publish dry-run (publication itself =
      owner action).
- [ ] T16 Apify actor wrapping corpus queries (PPE). Lives in actor-foundry; depends
      on corpus shape stabilizing (T12).

## Later

- [ ] T17 npm ecosystem (second runtime; mirrors T08–T12)
- [ ] T18 REST API with metering (only if usage signals justify; see ROADMAP M3–4)
