# ADR-001: PyPI Before npm

**Status:** Accepted

## Context
LibPulse must pick one ecosystem to prove the verification harness before
expanding. The two obvious candidates are PyPI (Python) and npm (JavaScript).

## Decision
Build the MVP on **PyPI first**. npm is phase 2 (see ROADMAP M5-6).

## Rationale
- **Single runtime already available** — the pipeline is written in Python 3.10.
  Verifying Python snippets needs no second toolchain; verifying npm would
  require Node + a JS execution path from day one.
- **uv speed** — `uv` creates version-pinned venvs and resolves/installs
  dependencies fast enough to verify many candidates per cycle on cheap compute.
  The verify step (install old, install new, run snippets) is the loop's
  bottleneck; uv keeps it cheap.
- **Cleaner version semantics** — PyPI version pinning (`pkg==X`) and the JSON
  API (`/pypi/<pkg>/json`) are simple and stable. No registry auth, no lockfile
  ambiguity, no peer-dependency resolution to model.
- **Breaking changes are well-signposted** — major Python libs document
  deprecations/removals in changelogs the LLM can analyze.

## Consequences
- Harness, verdict logic, and storage are PyPI-shaped first; npm support will
  add an ecosystem abstraction over watch + verify, not a rewrite.
- We accept a Python-only corpus for M0-M4. Demand for npm is deferred until the
  PyPI loop is proven self-sustaining and cheap.
