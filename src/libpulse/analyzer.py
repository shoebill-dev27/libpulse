"""Analyzer: turn a new release into candidate MigrationCase JSON files.

For each NewRelease the analyzer gathers public release context (PyPI metadata
plus GitHub release notes when the repo is discoverable), asks an LLM via the
Anthropic Messages API (raw HTTP, stdlib urllib — core stays dependency-free)
to propose breaking-change cases with executable before/after snippets, and
drops each candidate into data/cases/ for the verifier to judge. Candidates
are claims, not facts: only the execution verifier can promote them to the
corpus.

The pipeline must run WITHOUT an API key: when ANTHROPIC_API_KEY is unset the
analyzer reports itself disabled and produces nothing. The model comes from
LIBPULSE_MODEL (cheap model default) — never hardcoded at call sites.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Callable

from .models import MigrationCase
from .watcher import NewRelease, default_fetcher

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5"
USER_AGENT = "libpulse/0.1 (analyzer)"
GITHUB_RELEASES_URL = "https://api.github.com/repos/{repo}/releases?per_page=20"
TIMEOUT_S = 90
MAX_CONTEXT_CHARS = 15_000
MAX_CASES_PER_RELEASE = 5

# Structured-output schema: the API guarantees the reply parses against this.
_CASES_SCHEMA = {
    "type": "object",
    "properties": {
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "before_snippet": {"type": "string"},
                    "after_snippet": {"type": "string"},
                    "extra_requires": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "before_snippet", "after_snippet", "extra_requires"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cases"],
    "additionalProperties": False,
}

_PROMPT_TEMPLATE = """\
You analyze Python package release notes to extract BREAKING CHANGES as executable evidence.

Package: {package}
Old version: {old_version}
New version: {new_version}

Release context (PyPI metadata and release notes; may be incomplete):
---
{context}
---

Propose at most {max_cases} migration cases. Each case is one claimed breaking change:
- before_snippet: a short standalone Python script that PASSES (exit 0) on {package}=={old_version}
  and FAILS (raises / exits non-zero) on {package}=={new_version}. It must demonstrate the old API.
- after_snippet: the migrated script that PASSES on {package}=={new_version}.
- Snippets may import only the stdlib and {package} (plus extra_requires you list).
- Use assertions or let exceptions propagate to signal failure; print nothing on success.
- title: one line naming the removed/changed API.

Only claim changes supported by the context above. If the release contains no
verifiable breaking change (pure bugfix/feature release), return an empty list.
"""


def _http_json(
    url: str, headers: dict[str, str], payload: dict | None = None, timeout: int = TIMEOUT_S
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https url)
        return json.loads(resp.read().decode("utf-8"))


def _github_repo_from_pypi(info: dict) -> str | None:
    """Extract an 'owner/repo' GitHub slug from PyPI project metadata, if any."""
    urls = dict(info.get("project_urls") or {})
    candidates = list(urls.values()) + [info.get("home_page") or ""]
    for url in candidates:
        m = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", url or "")
        if m:
            owner, repo = m.group(1), m.group(2)
            return f"{owner}/{repo.removesuffix('.git')}"
    return None


def _matching_release_notes(releases: list[dict], new_version: str) -> list[str]:
    """Bodies of GitHub releases whose tag matches new_version; newest few as fallback."""
    exact, recent = [], []
    for rel in releases:
        tag = str(rel.get("tag_name") or "").lstrip("vV")
        body = rel.get("body") or ""
        if not body:
            continue
        if tag == new_version or tag.endswith("/" + new_version):
            exact.append(f"## {rel.get('tag_name')}\n{body}")
        elif len(recent) < 2:
            recent.append(f"## {rel.get('tag_name')}\n{body}")
    return exact if exact else recent


class Analyzer:
    """LLM-backed candidate-case generator. Disabled (no-op) without an API key."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        http: Callable[..., dict] = _http_json,
        pypi_fetch: Callable[[str], dict] = default_fetcher,
        max_cases: int = MAX_CASES_PER_RELEASE,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model or os.getenv("LIBPULSE_MODEL", DEFAULT_MODEL)
        self.http = http
        self.pypi_fetch = pypi_fetch
        self.max_cases = max_cases

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def fetch_context(self, release: NewRelease) -> str:
        """Best-effort public context for a release; failures degrade to less context."""
        parts: list[str] = []
        repo = None
        try:
            info = self.pypi_fetch(release.package).get("info", {})
            summary = info.get("summary") or ""
            if summary:
                parts.append(f"PyPI summary: {summary}")
            repo = _github_repo_from_pypi(info)
        except Exception as exc:
            print(f"[analyze] {release.package}: pypi context error: {exc}", file=sys.stderr)
        if repo:
            try:
                releases = self.http(
                    GITHUB_RELEASES_URL.format(repo=repo),
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/vnd.github+json",
                    },
                )
                parts.extend(_matching_release_notes(list(releases), release.new_version))
            except Exception as exc:
                print(f"[analyze] {release.package}: github context error: {exc}", file=sys.stderr)
        return "\n\n".join(parts)[:MAX_CONTEXT_CHARS] or "(no release notes found)"

    def generate_cases(self, release: NewRelease, context: str) -> list[MigrationCase]:
        prompt = _PROMPT_TEMPLATE.format(
            package=release.package,
            old_version=release.prev_version,
            new_version=release.new_version,
            context=context,
            max_cases=self.max_cases,
        )
        response = self.http(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "User-Agent": USER_AGENT,
            },
            payload={
                "model": self.model,
                "max_tokens": 4096,
                "output_config": {"format": {"type": "json_schema", "schema": _CASES_SCHEMA}},
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        text = next(b["text"] for b in response["content"] if b["type"] == "text")
        raw_cases = json.loads(text)["cases"][: self.max_cases]
        source = f"pypi:{release.package}=={release.new_version}"
        return [
            MigrationCase(
                package=release.package,
                old_version=release.prev_version,
                new_version=release.new_version,
                title=c["title"],
                before_snippet=c["before_snippet"],
                after_snippet=c["after_snippet"],
                extra_requires=list(c.get("extra_requires") or []),
                source=source,
            )
            for c in raw_cases
        ]

    def analyze(self, release: NewRelease, cases_dir: str | Path) -> list[Path]:
        """Generate candidate cases for one release and write them to the queue dir.

        Returns the written paths. Raises nothing fatal upward by design choice of
        the caller (cycle catches per-release); here we let errors propagate so the
        caller can log them per release.
        """
        if not self.enabled:
            return []
        if not release.prev_version:
            # No old version to verify against — nothing provable, skip.
            return []
        context = self.fetch_context(release)
        cases = self.generate_cases(release, context)
        out_dir = Path(cases_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for case in cases:
            path = out_dir / f"{case.package}-{case.new_version}-{case.case_id}.json"
            path.write_text(
                json.dumps(case.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            written.append(path)
        return written
