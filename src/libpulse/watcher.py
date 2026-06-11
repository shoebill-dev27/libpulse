"""Release watcher: poll the PyPI JSON API for tracked packages and report new
final releases since the last cycle.

Stdlib-only (urllib). No API keys. Per-package fetch errors are caught, logged to
stderr, and skipped so a single bad package never crashes the cycle.

Version handling is intentionally minimal: we only accept FINAL releases whose
version is a simple dotted-numeric string (e.g. ``1.2.3``). Anything containing
pre-release / dev / post / local markers (``rc``, ``a``, ``b``, ``.dev``,
``.post``, ``+local``, ...) is skipped rather than risk mis-parsing PEP 440
without the ``packaging`` dependency. Comparison is a numeric tuple compare of
the dotted parts.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
USER_AGENT = "libpulse/0.1 (release watcher)"
TIMEOUT_S = 15

# A final release: one or more dot-separated non-negative integers, nothing else.
_FINAL_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")

Fetcher = Callable[[str], dict]


@dataclass
class NewRelease:
    """A final release newer than the recorded watermark for a package."""

    package: str
    prev_version: str
    new_version: str
    released_at: str  # ISO 8601 upload time of new_version, or "" if unknown

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "prev_version": self.prev_version,
            "new_version": self.new_version,
            "released_at": self.released_at,
        }


def default_fetcher(package: str) -> dict:
    """Fetch the PyPI JSON metadata for a package (stdlib urllib only)."""
    url = PYPI_JSON_URL.format(package=package)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 (https url)
        return json.loads(resp.read().decode("utf-8"))


def is_final_version(version: str) -> bool:
    """True for plain dotted-numeric versions; False for pre/dev/post/local."""
    return bool(_FINAL_VERSION_RE.match(version))


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def read_packages(packages_file: str | Path) -> list[str]:
    """Parse the package list file: one name per line, '#' comments and blanks ignored."""
    names: list[str] = []
    for raw in Path(packages_file).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def _final_releases(data: dict) -> list[tuple[str, str]]:
    """Extract (version, iso_upload_time) for final releases, sorted ascending.

    ``data["releases"]`` maps version -> list of upload files. We take the
    earliest upload time among a version's files as its release time.
    """
    releases = data.get("releases")
    if not isinstance(releases, dict):
        raise ValueError("malformed PyPI response: missing 'releases' object")
    out: list[tuple[str, str]] = []
    for version, files in releases.items():
        if not is_final_version(version):
            continue
        if not isinstance(files, list) or not files:
            # A version with no distribution files (e.g. yanked-empty) — skip.
            continue
        uploads = [f.get("upload_time_iso_8601") or f.get("upload_time") or "" for f in files]
        uploads = [u for u in uploads if u]
        released_at = min(uploads) if uploads else ""
        out.append((version, released_at))
    out.sort(key=lambda vt: _version_key(vt[0]))
    return out


def _is_significant_bump(prev: str, new: str) -> bool:
    """True when the major or minor component changes (patch-only bumps rarely break)."""
    p, n = _version_key(prev), _version_key(new)
    return p[:2] != n[:2]


def historical_pairs(
    package: str,
    data: dict,
    months: int = 12,
    include_patch: bool = False,
    now: float | None = None,
) -> list[NewRelease]:
    """Consecutive (prev -> new) final-release pairs whose new side falls in the window.

    Used by `backfill` to seed the corpus from release history. The oldest in-window
    release is still paired with its (possibly out-of-window) predecessor. Pairs where
    only the patch component changes are skipped unless include_patch is set. Releases
    without an upload time are treated as out of window. Returned newest-first.
    """
    finals = _final_releases(data)
    cutoff = time.strftime(
        "%Y-%m-%dT%H:%M:%S", time.gmtime((now or time.time()) - months * 30.44 * 86400)
    )
    pairs: list[NewRelease] = []
    for i in range(1, len(finals)):
        new_version, released_at = finals[i]
        if not released_at or released_at < cutoff:
            continue
        prev_version = finals[i - 1][0]
        if not include_patch and not _is_significant_bump(prev_version, new_version):
            continue
        pairs.append(NewRelease(package, prev_version, new_version, released_at))
    pairs.reverse()
    return pairs


def discover_new_releases(
    store,
    packages_file: str | Path,
    fetch: Fetcher = default_fetcher,
) -> list[NewRelease]:
    """Find final releases newer than each package's watermark.

    First run for a package (no watermark): record the latest final version as
    the watermark and report a single pair (prev = second-latest final, new =
    latest) — never flood the whole history.

    Subsequent runs: report every final version strictly newer than the
    watermark, then advance the watermark to the latest.
    """
    found: list[NewRelease] = []
    for package in read_packages(packages_file):
        try:
            data = fetch(package)
            finals = _final_releases(data)
        except Exception as exc:  # one bad package must not kill the cycle
            print(f"[watch] {package}: fetch/parse error: {exc}", file=sys.stderr)
            continue
        if not finals:
            continue

        latest_version, latest_at = finals[-1]
        watermark = store.get_watermark(package)

        if watermark is None:
            # First run: report only the single latest pair, no flood.
            prev = finals[-2][0] if len(finals) >= 2 else ""
            found.append(NewRelease(package, prev, latest_version, latest_at))
            store.set_watermark(package, latest_version)
            continue

        if not is_final_version(watermark):
            # Defensive: a stored watermark should always be final; treat as first run.
            prev = finals[-2][0] if len(finals) >= 2 else ""
            found.append(NewRelease(package, prev, latest_version, latest_at))
            store.set_watermark(package, latest_version)
            continue

        wm_key = _version_key(watermark)
        newer = [(v, at) for v, at in finals if _version_key(v) > wm_key]
        if not newer:
            continue
        prev = watermark
        for version, released_at in newer:
            found.append(NewRelease(package, prev, version, released_at))
            prev = version
        store.set_watermark(package, latest_version)

    return found
