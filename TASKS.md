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

- [x] T11 MCP server (stdio, official `mcp` SDK as `[mcp]` optional extra):
      `libpulse-mcp` with query_migrations(package, from_version?, to_version?) and
      list_packages(). Read logic in stdlib-only corpus.py; verified via a real
      JSON-RPC handshake against the live corpus.

## Next (MVP)
- [ ] T12 Seed corpus: curate top-50 package list; run loop over their releases from
      the last 12 months; triage verdicts. Depends: T10. (Bulk, parallelizable.)
      Progress: `backfill` command done; pilot over the curated-20 list running.
- [ ] T12a Changelog deep-fetch (discovered 2026-06-11): GitHub release bodies are
      often announce-only (pandas) or absent; follow project_urls Changelog links
      (raw .md/.rst on GitHub; docs HTML stripped via html.parser) to feed the
      analyzer concrete API changes. Raises yield without model escalation.
- [x] T13 Weekly report generator (`libpulse report`: corpus growth, yield,
      per-package table, flagged packages) + `prune-venvs` disk hygiene +
      scripts/cron.sh.example (crontab install = owner action, incurs daily cost).
- [ ] T13a Persist release timestamps so the report can measure freshness lag
      (release -> published). Discovered 2026-06-11.
- [x] T14 SECURITY_REVIEW.md written (threat model: LLM code execution, supply
      chain, prompt injection via release notes, secrets, published surfaces).
      Hardened now: wheels-only installs (--no-build), MCP package-name validation.
- [x] T14a Network-less snippet execution: unshare -rn wrapper, auto-detected,
      opt-out via LIBPULSE_NO_NET_ISOLATION. Integration tests pass under it.
- [x] T15 HF dataset export: `libpulse export-hf` builds dist/hf/ (train.jsonl +
      dataset card incl. SECURITY_REVIEW disclaimer, cc-by-4.0 working license).
      Upload/publication itself = owner action.
- [ ] T16 Apify actor wrapping corpus queries (PPE). Lives in actor-foundry; depends
      on corpus shape stabilizing (T12).

## Later

- [ ] T17 npm ecosystem (second runtime; mirrors T08–T12)
- [ ] T18 REST API with metering (only if usage signals justify; see ROADMAP M3–4)
