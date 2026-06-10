# CLAUDE.md — LibPulse

## What this project is

Execution-verified breaking-change/migration KB served to AI agents. Part of the
revenue-portfolio (see ~/claude-dev/revenue-portfolio/ for strategy & decision logs).
Pillar 1 of 3. Stability-first: the unattended loop is the deliverable, content rides it.

## Hard rules

- **Only VERIFIED entries are ever published.** Verification = real execution in
  version-pinned venvs (see src/libpulse/verifier.py docstring for the 3 proofs).
- The `cycle` command must never crash mid-cycle: per-case failures are logged & skipped.
- Core stays stdlib-only. New runtime dependencies need an ADR. (`mcp` SDK is the
  approved exception, as an optional extra, when the MCP server lands.)
- The pipeline must run WITHOUT an API key (verify-only mode). LLM generation is
  optional and uses LIBPULSE_MODEL (cheap model default) — never hardcode models.
- Snippets are executed locally: keep the scrubbed-env + timeout + tempdir isolation
  in run_snippet(); never relax it. Never pass real env vars into snippets.

## Commands

```bash
.venv/bin/python -m pytest -q -m "not integration"   # fast tests
.venv/bin/python -m pytest -q -m integration          # real venv builds (needs network)
.venv/bin/ruff check src tests && .venv/bin/black --check src tests
.venv/bin/libpulse cycle                               # the unattended loop
```

## Conventions

- Python 3.10, black/ruff, line length 100, dataclasses over pydantic (no deps).
- Corpus JSON under data/corpus/ is deterministic (sorted) — diffs must stay readable.
- Each milestone gets a commit; tests must pass before committing.
- TASKS.md is the work queue; keep it current (mark done, add discovered work).
