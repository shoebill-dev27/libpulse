# LibPulse — Risks

Likelihood / Impact: L / M / H. Tripwire = the observable signal that says
"act now" (re-scope, pivot, or kill).

| Risk | Likelihood | Impact | Mitigation | Tripwire |
|------|-----------|--------|-----------|----------|
| **WTP unproven** — no one pays for verified migration data | H | H | Free tier (MCP + HF dataset) builds reputation/distribution first; metered paid API only after usage signals; corpus+harness retained as licensable asset even at $0 revenue | 6 months of nonzero MCP/API usage but zero conversions at quarterly kill-review |
| **Agents self-verify (too-fast-AI)** — future agents run their own venv checks and don't need a curated corpus | M | H | Position as the pre-computed, freshness-driven cache (latency + cost saved vs each agent re-verifying); keep freshness lag low so we're ahead of any release | Public agent tooling ships built-in execution-verified migration lookup |
| **Free competitors** — docs-for-agents / MCP-docs services give breaking-change data away | H | M | The moat is *execution verification*, not docs aggregation; lead on % verified and freshness, not coverage breadth | A free service publishes execution-verified (not just scraped) migration recipes |
| **Snippet execution security** — LLM-generated code runs locally | M | H | Snippets only from our own pipeline (never user-submitted); subprocess isolation; per-snippet timeouts; temp working dirs; no secrets in env passed to snippets; documented residual risk (no full sandbox/VM in MVP) | Any snippet observed touching network/filesystem outside its temp dir, or a verify run hanging past timeout repeatedly |
| **PyPI API changes** — JSON API schema/endpoints change | L | M | Thin watch adapter isolates the API surface; corpus is API-independent; pin to documented `/pypi/<pkg>/json` shape | watch step returns malformed/empty results across all packages in a cycle |
| **Maintenance loop rot** — unattended cron silently degrades (stale deps, cheap-model drift, dead venvs) | M | H | Loop never crashes (log-and-skip); weekly auto-report surfaces yield + failure counts; monthly owner report read; quarterly kill-review | Weekly report shows declining % verified or rising UNVERIFIABLE rate across multiple cycles |
| **MCP protocol churn** — MCP spec shifts and breaks the server | M | M | Corpus is protocol-independent (ADR-004); publish layer is a thin adapter; REST/dataset are fallback channels | MCP clients fail to connect after a spec release; adapter rewrite needed |
