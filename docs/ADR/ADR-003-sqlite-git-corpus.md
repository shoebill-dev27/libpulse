# ADR-003: SQLite + JSON-in-Git Corpus

**Status:** Accepted

## Context
The pipeline needs durable storage for candidate entries, verdicts, and the
published corpus. Options: a hosted DB (Postgres/managed), or local SQLite plus
a JSON export committed to git.

## Decision
Use **SQLite** as the working store and a **JSON export committed to git** as the
canonical, distributable corpus. No hosted database.

## Rationale
- **Zero ops cost** — the project is solo + unattended, maintained by cron and
  cheap models. A managed DB adds recurring cost, credentials to rotate, and an
  external dependency that can fail the loop. SQLite is a file.
- **The corpus IS the asset** — even if revenue is $0, the verified corpus +
  harness is a licensable asset (monetization fallback). Keeping it as plain
  files in git makes it portable and ownable, not locked in a hosted service.
- **Diffable** — JSON-in-git gives a full, reviewable history of every entry
  change. The weekly report and any audit can diff commits to see what entered
  the corpus and when (feeds the freshness-lag metric).
- **Portable** — exports drop straight into HuggingFace dataset, Apify actor,
  and the MCP/REST layers without an ETL step out of a live DB.

## Consequences
- No concurrent multi-writer access — fine for a single unattended loop.
- Corpus size is bounded by what's reasonable to commit to git; top-N scope
  (PRD) keeps this comfortable for the foreseeable horizon. Revisit if/when the
  npm expansion balloons row counts.
- The git repo is the source of truth; SQLite can be rebuilt from the JSON
  export if corrupted.
