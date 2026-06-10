# ADR-002: Execution Verification (the moat)

**Status:** Accepted

## Context
Anyone can scrape changelogs or ask an LLM "what broke in version X?". That data
is cheap, abundant, and frequently **wrong**: changelogs omit breaks, LLMs
hallucinate migrations, and a plausible "after" snippet may not actually run.
LibPulse's only durable differentiator is that its data is **proven correct**.

## Decision
A candidate entry is only published if its claim is confirmed by **actual
execution in version-pinned venvs**, not by trusting the LLM or the changelog.

## Verification Procedure
For each candidate (package, old → new version, before/after snippets), in
isolated uv-managed venvs:
1. Run `before` on **old** version → must **pass**.
2. Run `before` on **new** version → must **fail** (proves a real break).
3. Run `after` on **new** version → must **pass** (proves the migration works).

## Verdict Types
- **VERIFIED** — all three checks hold. *Published.*
- **NOT_BREAKING** — `before` still passes on the new version → no real break;
  discard the claim.
- **BROKEN_RECIPE** — `before` fails on new (real break) but `after` also fails
  on new → migration is wrong; do not publish, flag for regeneration.
- **UNVERIFIABLE** — setup/install error (resolution failure, native build,
  timeout) → cannot judge; log and skip.

## Why Only VERIFIED Is Published
The product promise is "every entry is execution-proven." Publishing anything
else (especially BROKEN_RECIPE) would poison agent output and destroy the only
reason to choose LibPulse over a free changelog scrape. Non-VERIFIED verdicts
are retained internally as signal (yield metrics, regeneration queue) but never
served.

## Consequences
- Verification is the loop's cost center and bottleneck; cheap venv management
  (uv) is load-bearing (ADR-001).
- Yield (% VERIFIED) is a core metric and a quality tripwire (RISKS.md).
- Executing generated snippets locally is a security cost; mitigations in
  ADR-005 context and RISKS.md (subprocess isolation, timeouts, no secrets).
