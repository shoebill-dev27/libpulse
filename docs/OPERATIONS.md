# LibPulse — Operations

Unattended, solo-operated. Post-window the loop runs on cheap models + cron with
near-zero human input. The cycle **must never crash**: failures are logged and
skipped, never fatal.

## Commands
- **Full cycle** (with API key): `libpulse cycle`
  Runs watch → analyze → verify → store → export → (weekly) report.
- **Verify-only** (no API key): same `libpulse cycle` with `ANTHROPIC_API_KEY`
  unset → skips `analyze`, re-verifies and serves existing candidates (ADR-005).
- **Publish**: `libpulse-mcp` — MCP server over stdio; serves only VERIFIED.
  Needs the optional extra: `uv pip install -p .venv -e ".[mcp]"`.
  Tools: `list_packages()`, `query_migrations(package, from_version?, to_version?)`.
  Register with Claude Code:
  `claude mcp add libpulse -- ~/claude-dev/libpulse/.venv/bin/libpulse-mcp`
  (set `LIBPULSE_CORPUS_DIR=~/claude-dev/libpulse/data/corpus` if launched
  from another working directory).
- **Report**: `libpulse report` — regenerate the latest markdown report.

Model selection: `LIBPULSE_MODEL` (cheap default for the loop).

## Cron Cadence
- **Daily** — `libpulse cycle` (watch for new releases, analyze if key present,
  verify candidates, store, export corpus to `data/`, commit).
- **Weekly** — `libpulse report` writes a markdown report to `reports/`.
- **Monthly** — owner touchpoint: read the latest weekly report (~15 min).
- **Quarterly** — owner kill-review: decide continue / pivot / kill against
  metrics and RISKS tripwires.

## Weekly Report Contains
- Corpus size and delta since last report (new VERIFIED entries).
- **% verified** (yield) and verdict breakdown (VERIFIED / NOT_BREAKING /
  BROKEN_RECIPE / UNVERIFIABLE).
- **Freshness lag** — median release-to-published time.
- MCP/API call volume (when instrumented).
- Failed/skipped packages this period with reasons.
- Any tripwire flags from RISKS.md that fired.

## Failure Handling
- A package that fails to install, build, or verify is logged with its reason
  and **skipped**; the cycle continues for the rest.
- `UNVERIFIABLE` and `BROKEN_RECIPE` are recorded as data, not errors.
- An LLM/API failure during `analyze` degrades to verify-only for that cycle.
- No retries/quarantine beyond log-and-skip in MVP; recurring failures surface
  in the weekly report for owner review.

## Owner Touchpoints
- **Monthly (~15 min):** read the weekly report; no action unless a tripwire fired.
- **Quarterly:** kill-review — continue, pivot, or retire (corpus + harness kept
  as a licensable asset regardless).
