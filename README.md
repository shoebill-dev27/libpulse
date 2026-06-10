# LibPulse

Execution-verified knowledge base of library breaking changes and migration recipes,
built for AI agents and developer tools.

AI models have training cutoffs; library releases don't stop. LibPulse watches new
releases, generates candidate breaking-change entries with migration recipes, and —
the part that matters — **proves every entry by actually running it**:

1. the `before` snippet passes on the old version (the claim is well-formed),
2. the `before` snippet fails on the new version (the change is really breaking),
3. the `after` snippet passes on the new version (the recipe really migrates).

Only entries that survive all three executions are published. No trust-me data.

## Quickstart

```bash
uv venv .venv && uv pip install --python .venv/bin/python -e '.[dev]'

# Verify one case
.venv/bin/libpulse verify-case data/cases/numpy-2.0-float-alias.json

# Unattended loop: ingest queued cases, verify pending, export corpus, write report
.venv/bin/libpulse cycle
```

Requirements: Python ≥3.10, [uv](https://docs.astral.sh/uv/), network access to PyPI.

## Layout

- `src/libpulse/` — verifier (the core), store, CLI
- `data/cases/` — queue: candidate cases as JSON (written by the analyzer or by hand)
- `data/corpus/` — published asset: verified entries, deterministic JSON, committed to git
- `docs/` — PRD, MVP definition, ADRs, risks, operations, 12-month roadmap
- `reports/` — cycle reports (machine-written)

## Status

MVP in progress. Harness milestone reached: a real migration (NumPy 2.0 `np.float_`
removal) verified end-to-end through the unattended cycle. Next: release watcher,
LLM analyzer, MCP server. See `TASKS.md`.
