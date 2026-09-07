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

## Data

The published corpus lives in `data/corpus/` (one file per package) and is
mirrored as a Hugging Face dataset:

**[shoebill-dev27/libpulse-breaking-changes](https://huggingface.co/datasets/shoebill-dev27/libpulse-breaking-changes)** — cc-by-4.0

Current: **29 verified entries across 11 packages** (more-itertools, networkx,
numpy, packaging, pandas, pillow, pytest, redis, scipy, typer, urllib3). Every
entry passed the three executions above; entries that failed any of them are not
published.

## Status

The unattended loop runs daily: watch PyPI for new releases → generate candidate
cases → verify by execution → export corpus → write a report. Release watcher,
LLM analyzer, HF export, deprecation feed and license matrix are all in.
Not yet built: the MCP server, and freshness-lag reporting (T13a). See `TASKS.md`.

Caveat worth stating plainly: coverage is deliberately narrow (a curated package
list) and the corpus grows only when a tracked package ships a real breaking
change. This is a small, high-confidence dataset, not a comprehensive one.

## License

- **Corpus** (`data/corpus/`, and the Hugging Face dataset): **CC BY 4.0** — use it.
- **Code**: no open-source license yet; all rights reserved for now. Read it,
  file issues, but don't assume redistribution rights until a LICENSE lands.

Also see `SECURITY_REVIEW.md` — this project executes generated code snippets
locally in scrubbed, network-isolated, version-pinned environments. Read that
before running the loop yourself.
