# LibPulse — MVP Definition

The MVP proves the **moat** (execution verification) and the **unattended loop**
end-to-end on a single ecosystem (PyPI), built first per stability-first policy.

## Pipeline (built in this order)
1. **watch** — poll PyPI JSON API (no API keys) for new releases of tracked packages.
2. **analyze** — LLM generates candidate breaking-change entries + before/after
   migration snippets from release notes/changelogs. *(Optional — see ADR-005.)*
3. **verify** — in isolated uv-managed venvs: run `before` on old version (must
   pass), `before` on new version (must fail → proves breaking), `after` on new
   version (must pass).
4. **store** — SQLite + JSON export in `data/`; corpus committed to git.
5. **publish** — MCP server over stdio; serves only VERIFIED entries.
6. **report** — weekly markdown auto-report in `reports/`.

## Acceptance Criteria
- [ ] **1 real migration verified end-to-end** — a genuine breaking change in a
      real top-50 package reaches verdict `VERIFIED` via actual execution.
- [ ] **Unattended cycle command** — a single command runs watch → analyze →
      verify → store → export with **no human input** and exits cleanly.
- [ ] **Loop never crashes** — a failing/uninstallable package is logged and
      skipped; the cycle completes for the rest.
- [ ] **MCP server serves verified entries** — an MCP client can query by
      package/version and receive only VERIFIED entries with before/after recipes.
- [ ] **Verify-only mode** — pipeline runs with no `ANTHROPIC_API_KEY` set
      (re-verifies existing candidates) without error.
- [ ] **Corpus in git** — `data/` JSON export is committed and diffable.
- [ ] **Tests + lint pass** — pytest green; ruff + black clean.

## Out of MVP Scope
- npm / any non-PyPI ecosystem (phase 2).
- REST API and metering (M3-4).
- HuggingFace dataset export and Apify actor (M1-2).
- JetBrains / IDE plugins.
- Web UI / human-facing search.
- User-submitted entries or snippets.
- Auto-retry/quarantine queues beyond log-and-skip.
- Multi-package dependency-graph verification (single-package only).
