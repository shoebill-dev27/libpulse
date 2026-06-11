"""Read-side access to the exported corpus (data/corpus/*.json).

Stdlib-only: this is what distribution channels (MCP server, future API/dataset
exports) build on, so it must not drag in the optional `mcp` dependency.
Version filtering reuses the watcher's final-version semantics; bounds that are
not plain dotted-numeric versions are ignored rather than guessed at.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .watcher import _version_key, is_final_version

DEFAULT_CORPUS_DIR = "data/corpus"


def corpus_dir(override: str | Path | None = None) -> Path:
    return Path(override or os.getenv("LIBPULSE_CORPUS_DIR", DEFAULT_CORPUS_DIR))


def load_entries(package: str, corpus: str | Path | None = None) -> list[dict]:
    path = corpus_dir(corpus) / f"{package}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("entries", []))


def list_packages(corpus: str | Path | None = None) -> list[dict]:
    """One row per package in the corpus: name, entry count, newest covered version."""
    rows: list[dict] = []
    root = corpus_dir(corpus)
    if not root.exists():
        return rows
    for path in sorted(root.glob("*.json")):
        entries = load_entries(path.stem, corpus)
        if not entries:
            continue
        finals = [e["new_version"] for e in entries if is_final_version(e.get("new_version", ""))]
        latest = max(finals, key=_version_key) if finals else entries[-1].get("new_version", "")
        rows.append({"package": path.stem, "cases": len(entries), "latest_version": latest})
    return rows


def query_migrations(
    package: str,
    from_version: str | None = None,
    to_version: str | None = None,
    corpus: str | Path | None = None,
) -> dict:
    """Verified breaking changes that bite when upgrading package across the given range.

    An entry applies when its new_version is > from_version (the change is introduced
    after where you are) and <= to_version (you will cross it). A bound that is not a
    plain dotted-numeric version is ignored (permissive by design).
    """
    entries = load_entries(package, corpus)
    if from_version and is_final_version(from_version):
        lo = _version_key(from_version)
        entries = [
            e
            for e in entries
            if not is_final_version(e["new_version"]) or _version_key(e["new_version"]) > lo
        ]
    if to_version and is_final_version(to_version):
        hi = _version_key(to_version)
        entries = [
            e
            for e in entries
            if not is_final_version(e["new_version"]) or _version_key(e["new_version"]) <= hi
        ]
    return {
        "package": package,
        "from_version": from_version,
        "to_version": to_version,
        "count": len(entries),
        "entries": entries,
    }
