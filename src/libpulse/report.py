"""Weekly markdown report: corpus growth, verdict mix, problem packages.

This is the owner's ~15-minute monthly touchpoint material and the input to
quarterly kill-reviews, generated unattended (cron, T13).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .store import Store

WINDOW_DAYS = 7


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def _parse_iso_epoch(value: str) -> float | None:
    """Parse an ISO 8601 timestamp to epoch seconds (UTC); None if unparseable."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _freshness_line(store: Store) -> str:
    """One-line release->verified lag summary over timestamped verified cases."""
    rows = store.conn.execute(
        """SELECT c.released_at, r.verified_at FROM cases c JOIN results r USING(case_id)
           WHERE r.verdict='verified' AND c.released_at != ''"""
    ).fetchall()
    lags_days: list[float] = []
    for row in rows:
        released = _parse_iso_epoch(row["released_at"])
        if released is None:
            continue
        lags_days.append((row["verified_at"] - released) / 86400)
    if not lags_days:
        return "- Freshness lag: no timestamped verified cases yet."
    lags_days.sort()
    n = len(lags_days)
    median = lags_days[n // 2] if n % 2 else (lags_days[n // 2 - 1] + lags_days[n // 2]) / 2
    return (
        f"- Freshness lag (release→verified): median {round(median)}d, "
        f"max {round(max(lags_days))}d, over {n} timestamped verified case(s)."
    )


def _deprecation_line(corpus_dir: str | None = None) -> str:
    """One-line deprecation-signal summary from the corpus (offline, no network)."""
    from . import corpus as corpus_mod
    from .deprecations import from_corpus

    packages = [row["package"] for row in corpus_mod.list_packages(corpus_dir)]
    records = from_corpus(packages, corpus_dir)
    if not records:
        return "- Deprecation signals: none found in the corpus yet."
    affected = sorted({r.package for r in records})
    return (
        f"- Deprecation signals: {len(records)} across {len(affected)} package(s) "
        f"({', '.join(affected)}). Run `libpulse deprecations` for the full feed."
    )


def build_report(store: Store, now: float | None = None, window_days: int = WINDOW_DAYS) -> str:
    now = now or time.time()
    since = now - window_days * 86400
    totals = store.verdict_counts()
    judged = sum(totals.values())
    verified = totals.get("verified", 0)

    rows = store.conn.execute(
        """SELECT c.package,
                  COUNT(*) AS judged,
                  SUM(r.verdict = 'verified') AS verified,
                  SUM(r.verdict = 'unverifiable') AS unverifiable,
                  SUM(r.verified_at >= ?) AS judged_this_window
           FROM cases c JOIN results r USING(case_id)
           GROUP BY c.package ORDER BY verified DESC, judged DESC""",
        (since,),
    ).fetchall()
    new_verified = store.conn.execute(
        "SELECT COUNT(*) n FROM results WHERE verdict='verified' AND verified_at >= ?",
        (since,),
    ).fetchone()["n"]
    pending = len(store.pending_case_ids())

    lines = [
        f"# LibPulse weekly report — {time.strftime('%Y-%m-%d', time.localtime(now))}",
        "",
        f"- Corpus: **{verified} verified** cases ({new_verified:+d} in the last "
        f"{window_days} days); {pending} candidate(s) pending verification.",
        f"- All-time yield: {verified}/{judged} judged ({_pct(verified, judged)}). "
        f"Verdict mix: {dict(sorted(totals.items()))}.",
        "",
        "| package | verified | judged | unverifiable | judged last 7d |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['package']} | {r['verified'] or 0} | {r['judged']} "
            f"| {r['unverifiable'] or 0} | {r['judged_this_window'] or 0} |"
        )
    flagged = [r["package"] for r in rows if r["judged"] >= 3 and not (r["verified"] or 0)]
    lines += [
        "",
        "## Attention",
        (
            "- Packages with ≥3 judged candidates and 0 verified (snippet/harness "
            f"accommodation needed): {', '.join(flagged)}"
            if flagged
            else "- No packages flagged."
        ),
        _freshness_line(store),
        _deprecation_line(),
        "",
    ]
    return "\n".join(lines)


def write_report(store: Store, reports_dir: str | Path = "reports", now: float | None = None):
    now = now or time.time()
    path = Path(reports_dir) / f"weekly_{time.strftime('%Y-%m-%d', time.localtime(now))}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(store, now), encoding="utf-8")
    return path
