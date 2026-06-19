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
- [x] T12a Changelog deep-fetch (analyzer): when the GitHub releases API yields no
      usable notes (no discoverable repo, or empty release bodies), follow a
      `project_urls` changelog link (Changelog / Release Notes / History / News /
      What's New) and extract the section for the new version. Raw `.md/.rst/.txt`
      used as-is; HTML stripped via stdlib `html.parser` (script/style/head dropped).
      Section extraction isolates the version's block up to the next version heading,
      falling back to the head (changelogs are reverse-chronological) when the
      version is absent. Raises analyzer yield without model escalation for packages
      that publish notes only in a CHANGELOG file. Injectable `text_fetch` keeps
      tests network-free (7 new tests; full suite 81).
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
- [x] T16 Apify actors wrapping corpus queries: done in ~/claude-dev/actor-foundry
      (changelog-diff + dependency-migration-check, bundled corpus snapshot).
      PPE pricing happens at publish (owner, actor-foundry A04).
- [x] T19 Deprecation feed (`libpulse deprecations`): time-ordered deprecation
      signals across tracked packages, from two sources — the verified corpus
      (offline) and PyPI info.description/summary (injectable fetcher). Regex
      extracts api token + deprecated_in/removed_in version hints; de-duped,
      newest-first. Writes reports/deprecations.md + data/deprecations.json;
      `--no-pypi` for offline. report.py shows a one-line corpus summary.
      Where the corpus says "what broke", this says "what is about to break".
- [x] T20 License matrix (`libpulse license-matrix`): per tracked package, its
      normalized SPDX-ish license (info.license + Trove classifiers) and the
      licenses of its direct dependencies (requires_dist, extras skipped).
      Flags permissive→copyleft (GPL/AGPL/LGPL) combos as a redistribution risk.
      Writes reports/license_matrix.md + data/license_matrix.json. T19/T20 are
      network-free in tests via injected fetchers (14 new tests; full suite 66).
- [x] T21 CI failure taxonomy (`libpulse failure-taxonomy`): classifies HOW each
      verified breaking change manifests by reading the `before_on_new` step's
      stderr in the store — import-error / removed-api / signature-change /
      behavior-change / deprecation / syntax-error / env-error / unknown. Pure
      string-matching classifier + store aggregation; writes
      reports/failure_taxonomy.md + data/failure_taxonomy.json, report.py shows a
      one-line summary. Completes the A02/A04 near-miss data-asset trio
      (deprecation feed + license matrix + failure taxonomy). Offline, 8 new
      tests (full suite 74). Live store: 29 verified cases classified
      (removed-api 10, behavior-change 9, signature-change 4, import-error 3).

## Later

- [ ] T17 npm ecosystem (second runtime; mirrors T08–T12)
- [ ] T18 REST API with metering (only if usage signals justify; see ROADMAP M3–4)
