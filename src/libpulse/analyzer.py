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
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from .models import MigrationCase
from .watcher import NewRelease, _is_significant_bump, default_fetcher, is_final_version

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5"
# When the cheap model yields zero candidates on a major/minor bump, retry once
# with this model (observed: post-cutoff releases need the stronger model's
# knowledge). Set LIBPULSE_FALLBACK_MODEL equal to LIBPULSE_MODEL to disable.
DEFAULT_FALLBACK_MODEL = "claude-sonnet-4-6"
USER_AGENT = "libpulse/0.1 (analyzer)"
GITHUB_RELEASES_URL = "https://api.github.com/repos/{repo}/releases?per_page=20"
TIMEOUT_S = 90
MAX_CONTEXT_CHARS = 15_000
MAX_CASES_PER_RELEASE = 5
# Deep-fetch: when GitHub release notes are empty/missing, follow a changelog
# link from PyPI project_urls and extract the section for the new version.
CHANGELOG_FETCH_TIMEOUT_S = 20
MAX_CHANGELOG_CHARS = 8_000
# project_urls labels that point at a human changelog (matched case-insensitively).
_CHANGELOG_LABEL_RE = re.compile(
    r"change\s*log|change\s*history|^changes$|release\s*notes|^history$|^news$|what'?s\s*new",
    re.IGNORECASE,
)

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

Precision rules (cases failing these are rejected by an execution harness, so be strict):
- Only claim changes you are CERTAIN take effect exactly in {new_version}. A deprecation
  is NOT a breaking change: if the old API still runs (even with a warning) in
  {new_version}, do not include it.
- The before_snippet's failure on {new_version} must come from the changed API itself
  (AttributeError/TypeError/etc.), not from your own assertions. Call the old API in the
  simplest documented way; do not assert on return types, dtypes, or values unless the
  documented change is about them.
- Never invent keyword arguments or behaviors; if unsure how an API behaved in
  {old_version}, drop the case.
- The before_snippet may use ONLY APIs that already exist in {old_version}; it must
  not reference anything introduced in {new_version}.

Snippet environment rules (the harness runs snippets as standalone scripts in a
sandbox with only loopback networking):
- Snippets must be fully self-contained. Frameworks needing global setup must do it
  inline, e.g. django: `from django.conf import settings; settings.configure();
  import django; django.setup()` before touching any settings-dependent API.
- Drive CLI frameworks in-process (e.g. `click.testing.CliRunner().invoke(...)`),
  never via subprocess.
- No external network access. Local 127.0.0.1 server fixtures are allowed but must
  always shut down/terminate so the script exits promptly.

Ground claims in the context when possible. When the context only announces a major
release without listing concrete API changes, you may also propose breaking changes you
confidently KNOW land exactly in {new_version} of {package} from your own knowledge —
every case is execution-verified downstream, so a wrong claim is cheap, but do not pad
the list with guesses. If you know of no verifiable breaking change (pure bugfix/feature
release), return an empty list.
"""


def _http_json(
    url: str, headers: dict[str, str], payload: dict | None = None, timeout: int = TIMEOUT_S
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https url)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # The body carries the only actionable part. Bare HTTPError stringifies
        # to "HTTP Error 400: Bad Request", which is what the cycle logged every
        # night from 2026-07-23 while the real message was "credit balance is
        # too low" — 7 weeks of zero candidates with the reason one layer down.
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:400]
        except Exception:  # noqa: BLE001 - a body we cannot read must not mask the HTTP error
            pass
        raise urllib.error.HTTPError(
            exc.url, exc.code, f"{exc.reason}: {body}" if body else exc.reason, exc.headers, None
        ) from exc


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


def _http_text(url: str, timeout: int = CHANGELOG_FETCH_TIMEOUT_S) -> str:
    """Fetch a URL as decoded text (stdlib urllib). Used for changelog deep-fetch."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (https url)
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def _changelog_url_from_pypi(info: dict) -> str | None:
    """Return a changelog/release-notes URL from PyPI project_urls, if labelled as one."""
    for label, url in dict(info.get("project_urls") or {}).items():
        if url and _CHANGELOG_LABEL_RE.search(str(label)):
            return str(url)
    return None


class _TextExtractor(HTMLParser):
    """Collect visible text from an HTML page, dropping script/style content."""

    _SKIP = {"script", "style", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        return "\n".join(self._parts)


def _looks_like_html(url: str, body: str) -> bool:
    if url.lower().rsplit("?", 1)[0].endswith((".md", ".rst", ".txt")):
        return False
    head = body[:512].lstrip().lower()
    return head.startswith("<!doctype html") or head.startswith("<html") or "<body" in head


def _changelog_to_text(url: str, body: str) -> str:
    return _strip_html(body) if _looks_like_html(url, body) else body


def _strip_html(body: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(body)
    except Exception:  # malformed markup: keep whatever was parsed so far
        pass
    return parser.text()


def _is_version_heading(line: str, version: str) -> bool:
    """True if the line introduces a changelog entry for the given version."""
    stripped = line.lstrip("#=-* \t").strip()
    stripped = stripped.lstrip("[vV").strip()  # keep-a-changelog "## [2.0.0]" / "v2.0.0"
    return (
        stripped == version
        or stripped.startswith(version + " ")
        or stripped.startswith(version + "]")
    )


def _extract_version_section(text: str, version: str) -> str:
    """The changelog block for `version`: from its heading to the next version heading.

    Falls back to the head of the changelog (changelogs are reverse-chronological,
    so the top is the newest) when the exact version heading is not found.
    """
    lines = text.splitlines()
    other_version = re.compile(r"^[#=\-*\s\[vV]*\d+\.\d+")
    start = next((i for i, ln in enumerate(lines) if _is_version_heading(ln, version)), None)
    if start is None:
        return text[:MAX_CHANGELOG_CHARS]
    out = [lines[start]]
    for ln in lines[start + 1 :]:
        if other_version.match(ln) and not _is_version_heading(ln, version):
            break
        out.append(ln)
    return "\n".join(out)[:MAX_CHANGELOG_CHARS]


class Analyzer:
    """LLM-backed candidate-case generator. Disabled (no-op) without an API key."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        http: Callable[..., dict] = _http_json,
        pypi_fetch: Callable[[str], dict] = default_fetcher,
        max_cases: int = MAX_CASES_PER_RELEASE,
        fallback_model: str | None = None,
        text_fetch: Callable[[str], str] = _http_text,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model or os.getenv("LIBPULSE_MODEL", DEFAULT_MODEL)
        self.fallback_model = (
            fallback_model
            if fallback_model is not None
            else os.getenv("LIBPULSE_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)
        )
        self.http = http
        self.pypi_fetch = pypi_fetch
        self.max_cases = max_cases
        self.text_fetch = text_fetch

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _should_escalate(self, release: NewRelease) -> bool:
        if not self.fallback_model or self.fallback_model == self.model:
            return False
        if not (is_final_version(release.prev_version) and is_final_version(release.new_version)):
            return False
        return _is_significant_bump(release.prev_version, release.new_version)

    def fetch_context(self, release: NewRelease) -> str:
        """Best-effort public context for a release; failures degrade to less context."""
        parts: list[str] = []
        repo = None
        info: dict = {}
        try:
            info = self.pypi_fetch(release.package).get("info", {})
            summary = info.get("summary") or ""
            if summary:
                parts.append(f"PyPI summary: {summary}")
            repo = _github_repo_from_pypi(info)
        except Exception as exc:
            print(f"[analyze] {release.package}: pypi context error: {exc}", file=sys.stderr)
        notes_found = False
        if repo:
            try:
                releases = self.http(
                    GITHUB_RELEASES_URL.format(repo=repo),
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/vnd.github+json",
                    },
                )
                notes = _matching_release_notes(list(releases), release.new_version)
                parts.extend(notes)
                notes_found = bool(notes)
            except Exception as exc:
                print(f"[analyze] {release.package}: github context error: {exc}", file=sys.stderr)
        # GitHub gave us nothing usable: follow a project_urls changelog link and
        # extract the section for the new version (raw .md/.rst as-is; HTML stripped).
        if not notes_found:
            section = self._fetch_changelog_section(release, info)
            if section:
                parts.append(section)
        return "\n\n".join(parts)[:MAX_CONTEXT_CHARS] or "(no release notes found)"

    def _fetch_changelog_section(self, release: NewRelease, info: dict) -> str:
        url = _changelog_url_from_pypi(info)
        if not url:
            return ""
        try:
            body = self.text_fetch(url)
        except Exception as exc:
            print(f"[analyze] {release.package}: changelog fetch error: {exc}", file=sys.stderr)
            return ""
        section = _extract_version_section(_changelog_to_text(url, body), release.new_version)
        section = section.strip()
        return f"Changelog ({url}):\n{section}" if section else ""

    def generate_cases(
        self, release: NewRelease, context: str, model: str | None = None
    ) -> list[MigrationCase]:
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
                "model": model or self.model,
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
                released_at=release.released_at,
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
        if not cases and self._should_escalate(release):
            print(
                f"[analyze] {release.package} {release.new_version}: "
                f"0 candidates from {self.model}, retrying with {self.fallback_model}",
                file=sys.stderr,
            )
            cases = self.generate_cases(release, context, model=self.fallback_model)
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
