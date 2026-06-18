"""License matrix: per tracked package, its normalized license and the licenses
of its direct dependencies, flagging permissive→copyleft combinations that are a
real legal-risk signal for downstream redistributors.

Stdlib-only. PyPI metadata is fetched through the watcher's injectable fetcher,
so tests pass canned data and stay offline. License normalization is a small,
documented SPDX-ish mapping; anything unrecognized becomes "UNKNOWN" rather than
being guessed at.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .watcher import Fetcher, default_fetcher

# Substrings (lower-cased) -> SPDX-ish token. Order matters: more specific first.
_LICENSE_PATTERNS: list[tuple[str, str]] = [
    ("apache", "Apache-2.0"),
    ("mit", "MIT"),
    ("bsd 3", "BSD-3-Clause"),
    ("bsd-3", "BSD-3-Clause"),
    ("bsd 2", "BSD-2-Clause"),
    ("bsd-2", "BSD-2-Clause"),
    ("bsd", "BSD"),
    ("isc", "ISC"),
    ("mozilla", "MPL-2.0"),
    ("mpl", "MPL-2.0"),
    ("lesser general public", "LGPL"),
    ("lgpl", "LGPL"),
    ("affero", "AGPL"),
    ("agpl", "AGPL"),
    ("gnu general public", "GPL"),
    ("gpl", "GPL"),
    ("python software foundation", "PSF-2.0"),
    ("psf", "PSF-2.0"),
    ("unlicense", "Unlicense"),
    ("public domain", "Unlicense"),
]
# Strong/weak copyleft tokens that create obligations for redistributors.
_COPYLEFT = {"GPL", "AGPL", "LGPL"}
_PERMISSIVE = {"MIT", "BSD", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "ISC", "Unlicense"}

_REQ_NAME = re.compile(r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")


def normalize_license(info: dict) -> str:
    """Best-effort SPDX-ish token from info.license + Trove classifiers."""
    candidates: list[str] = []
    if info.get("license"):
        candidates.append(str(info["license"]))
    for classifier in info.get("classifiers") or []:
        if classifier.startswith("License ::"):
            candidates.append(classifier)
    blob = " ".join(candidates).lower()
    for needle, token in _LICENSE_PATTERNS:
        if needle in blob:
            return token
    return "UNKNOWN"


def direct_dependencies(info: dict) -> list[str]:
    """Bare distribution names from info.requires_dist (no version/extras/markers)."""
    names: list[str] = []
    seen: set[str] = set()
    for req in info.get("requires_dist") or []:
        # Skip optional/extra dependencies (they are not installed by default).
        if "extra ==" in req or "; extra" in req:
            continue
        m = _REQ_NAME.match(req.strip())
        if not m:
            continue
        name = m.group(1)
        low = name.lower()
        if low not in seen:
            seen.add(low)
            names.append(name)
    return names


@dataclass
class PackageLicense:
    package: str
    license: str
    dependencies: list[dict]  # [{"name": str, "license": str}]
    copyleft_conflict: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _license_of(package: str, fetch: Fetcher, cache: dict[str, str]) -> str:
    low = package.lower()
    if low in cache:
        return cache[low]
    try:
        info = fetch(package).get("info", {}) or {}
        token = normalize_license(info)
    except Exception:
        token = "UNKNOWN"
    cache[low] = token
    return token


def build_matrix(packages: list[str], *, fetch: Fetcher = default_fetcher) -> dict:
    """License matrix for packages and their direct dependencies."""
    cache: dict[str, str] = {}
    rows: list[PackageLicense] = []
    for package in packages:
        try:
            info = fetch(package).get("info", {}) or {}
        except Exception:
            continue
        pkg_license = normalize_license(info)
        cache[package.lower()] = pkg_license
        deps: list[dict] = []
        conflict = False
        for dep_name in direct_dependencies(info):
            dep_license = _license_of(dep_name, fetch, cache)
            deps.append({"name": dep_name, "license": dep_license})
            if pkg_license in _PERMISSIVE and dep_license in _COPYLEFT:
                conflict = True
        rows.append(PackageLicense(package, pkg_license, deps, conflict))
    return {
        "packages": [r.to_dict() for r in rows],
        "conflicts": sum(1 for r in rows if r.copyleft_conflict),
    }


def render_markdown(matrix: dict) -> str:
    lines = [
        f"# LibPulse license matrix — {matrix['conflicts']} copyleft conflict(s)",
        "",
        "A conflict flags a permissively-licensed package with a copyleft "
        "(GPL/AGPL/LGPL) direct dependency — a redistribution risk worth review.",
        "",
        "| package | license | copyleft conflict | dependencies (license) |",
        "|---|---|---|---|",
    ]
    for row in matrix["packages"]:
        deps = ", ".join(f"{d['name']} ({d['license']})" for d in row["dependencies"]) or "—"
        flag = "⚠️ yes" if row["copyleft_conflict"] else "no"
        lines.append(f"| {row['package']} | {row['license']} | {flag} | {deps} |")
    lines.append("")
    return "\n".join(lines)
