# ADR-004: MCP-First Distribution

**Status:** Accepted

## Context
The verified corpus can be exposed many ways: an MCP server, a REST API, a
HuggingFace dataset, or a human-facing search website. We must pick the first
distribution channel to build in the M0 window.

## Decision
Ship an **MCP server over stdio** as the first distribution channel. REST API,
dataset export, and any website come later.

## Rationale
- **Demand is moving to machines** — the consumers who most need post-cutoff,
  verified migration data are AI agents, and agent tooling is standardizing on
  MCP. Serving the data where agents already look maximizes fit.
- **Human-facing search is declining** — AI Overviews and chat-based answers are
  eroding click-through to docs/search sites. Betting on a human search UI is
  betting on a shrinking channel; a website would be high-effort, low-leverage.
- **Zero marginal hosting** — stdio MCP runs in the client's process space.
  There's no server to host, scale, or pay for. This fits the zero-ops,
  unattended, solo-operated constraint better than standing up a REST endpoint.
- **Tightest feedback loop** — the same person building agents can wire LibPulse
  in immediately and feel whether the data is useful, before investing in
  metered infrastructure.

## Consequences
- The publish layer targets the MCP tool/resource contract first; REST reuses
  the same store and serializers when usage justifies metering (ROADMAP M3-4).
- We accept no public human-browsable surface in MVP; the HuggingFace dataset
  (M1-2) covers reputation/discovery for humans instead.
- MCP protocol churn is a tracked risk (RISKS.md); the corpus is protocol-
  independent, so a protocol shift is an adapter change, not a data loss.
