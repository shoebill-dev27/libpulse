"""Deprecation feed: a time-ordered list of deprecation signals across tracked
packages, derived from two sources and de-duplicated:

  (a) the verified corpus (data/corpus/*.json): scan case titles and snippets
      for deprecation language;
  (b) PyPI metadata (info.description / info.summary) fetched per package via
      the watcher's injectable fetcher.

Stdlib-only and offline-testable: the corpus source needs no network, and the
PyPI source takes an injectable fetcher so tests pass canned metadata. This is
a natural expansion of the corpus: where the corpus answers "what broke", the
deprecation feed answers "what is *about* to break".
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from . import corpus
from .watcher import Fetcher, default_fetcher

# Lines mentioning any of these are candidate deprecation signals.
_SIGNAL = re.compile(
    r"deprecat|will be removed|pending removal|PendingDeprecationWarning|"
    r"DeprecationWarning|scheduled for removal|removed in|no longer (?:supported|available)",
    re.IGNORECASE,
)
_API_BACKTICK = re.compile(r"`([A-Za-z_][\w.]*)`")
_API_QUOTED = re.compile(r"['\"]([A-Za-z_][\w.]+)['\"]")
_API_DOTTED = re.compile(r"\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)\b")
_VER_DEPRECATED = re.compile(r"deprecated\s+(?:since\s+|in\s+)?v?(\d+(?:\.\d+)+)", re.IGNORECASE)
_VER_REMOVED = re.compile(r"(?:removed|removal)\s+in\s+v?(\d+(?:\.\d+)+)", re.IGNORECASE)
_MAX_MESSAGE = 240


@dataclass
class DeprecationRecord:
    package: str
    api: str  # the deprecated symbol/feature if extractable, else ""
    message: str
    deprecated_in: str  # version string or ""
    removed_in: str  # version string or ""
    source: str  # provenance: "corpus", a URL, or "pypi"
    released_at: str  # ISO 8601, for ordering ("" sorts last)

    def to_dict(self) -> dict:
        return asdict(self)

    def key(self) -> tuple[str, str, str]:
        return (self.package, self.api, self.message)


def _extract_api(line: str) -> str:
    for pattern in (_API_BACKTICK, _API_QUOTED, _API_DOTTED):
        m = pattern.search(line)
        if m:
            return m.group(1)
    return ""


def _scan_text(text: str, package: str, source: str, released_at: str) -> list[DeprecationRecord]:
    """Pull one record per line that carries a deprecation signal."""
    records: list[DeprecationRecord] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or not _SIGNAL.search(line):
            continue
        dep = _VER_DEPRECATED.search(line)
        rem = _VER_REMOVED.search(line)
        records.append(
            DeprecationRecord(
                package=package,
                api=_extract_api(line),
                message=line[:_MAX_MESSAGE],
                deprecated_in=dep.group(1) if dep else "",
                removed_in=rem.group(1) if rem else "",
                source=source,
                released_at=released_at,
            )
        )
    return records


def from_corpus(packages: list[str], corpus_dir: str | None = None) -> list[DeprecationRecord]:
    records: list[DeprecationRecord] = []
    for package in packages:
        for entry in corpus.load_entries(package, corpus_dir):
            blob = "\n".join(
                str(entry.get(field, "")) for field in ("title", "before", "after", "source")
            )
            src = entry.get("source") or "corpus"
            records.extend(_scan_text(blob, package, src, entry.get("released_at", "")))
    return records


def from_pypi(packages: list[str], fetch: Fetcher = default_fetcher) -> list[DeprecationRecord]:
    records: list[DeprecationRecord] = []
    for package in packages:
        try:
            info = fetch(package).get("info", {}) or {}
        except Exception:  # one bad package must not break the feed
            continue
        text = "\n".join([info.get("summary") or "", info.get("description") or ""])
        records.extend(_scan_text(text, package, "pypi", ""))
    return records


def build_feed(
    packages: list[str],
    *,
    corpus_dir: str | None = None,
    fetch: Fetcher = default_fetcher,
    scan_pypi: bool = True,
    limit: int | None = None,
) -> list[DeprecationRecord]:
    """Combine corpus + PyPI deprecation signals, de-dupe, order newest-first."""
    records = from_corpus(packages, corpus_dir)
    if scan_pypi:
        records.extend(from_pypi(packages, fetch))
    seen: set[tuple[str, str, str]] = set()
    unique: list[DeprecationRecord] = []
    for rec in records:
        if rec.key() in seen:
            continue
        seen.add(rec.key())
        unique.append(rec)
    # Newest first; records without a date sort last (empty string < any date,
    # so reverse=True would put them first — guard with a presence flag).
    unique.sort(key=lambda r: (r.released_at != "", r.released_at), reverse=True)
    return unique[:limit] if limit is not None else unique


def render_markdown(records: list[DeprecationRecord]) -> str:
    lines = [
        f"# LibPulse deprecation feed — {len(records)} signal(s)",
        "",
        "| package | api | deprecated in | removed in | released | message |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        msg = r.message.replace("|", "\\|")
        lines.append(
            f"| {r.package} | {r.api or '—'} | {r.deprecated_in or '—'} "
            f"| {r.removed_in or '—'} | {r.released_at or '—'} | {msg} |"
        )
    lines.append("")
    return "\n".join(lines)
