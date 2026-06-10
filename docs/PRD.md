# LibPulse — PRD

## Problem
AI models and agents have training cutoffs. Library releases shipped after the
cutoff — especially **breaking changes** — are permanently outside their
knowledge. When an agent writes or upgrades code against a recent library
version, it hallucinates old APIs or proposes migrations that don't compile.
Release notes and changelogs are unstructured, often wrong, and never
execution-tested. There is no machine-readable, **verified**, fresh source of
"what broke and how to migrate" that an agent can query.

## Value Proposition
A continuously-updated knowledge base of library breaking changes and migration
recipes where **every published entry has been proven by execution**: the old
code runs on the old version, fails on the new version, and the migrated code
runs on the new version. Fresh (polled from release feeds), machine-first
(served over MCP), and committed to git as a diffable, portable corpus.

## Users
- **AI agents (via MCP)** — primary. Query during code-gen/upgrade tasks for
  verified breaking-change + migration data on a given package/version.
- **Dev-tool builders (via API / Apify actor)** — embed the data into IDE
  plugins, CI upgrade bots, code-mod tools. Phase 2.
- **Developers (via dataset)** — consume the HuggingFace dataset for research,
  fine-tuning, or offline lookup. Reputation/distribution channel.

## Scope (MVP)
Python / PyPI ecosystem, top ~50 packages, releases from the last 12 months
forward. See `MVP.md`. npm is phase 2.

## Success Metrics
- **Corpus size** — count of VERIFIED entries.
- **% verified** — VERIFIED / total candidate entries generated (verification
  yield; tracks moat quality).
- **MCP / API calls** — query volume (demand signal).
- **Freshness lag** — median time from package release to published verified
  entry. Target: days, not weeks; the unattended loop drives this down.

## Non-Goals
- Not a general docs/search site for humans (machine-first; see ADR-004).
- Not a vulnerability/CVE database (that's covered elsewhere).
- Not exhaustive coverage of every PyPI package — top-N, demand-driven.
- Not user-submitted snippets (security: we only execute our own pipeline output).
- Not a hosted code-execution service — verification is internal only.
- No sales motion, no SNS marketing, no human support SLA.
