"""Weekly markdown report: corpus growth, verdict mix, problem packages.

This is the owner's ~15-minute monthly touchpoint material and the input to
quarterly kill-reviews, generated unattended (cron, T13).
"""

from __future__ import annotations

import time
from pathlib import Path

from .store import Store

WINDOW_DAYS = 7


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


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
        "- Freshness lag: not yet measured (release timestamp not persisted; TODO T13a).",
        "",
    ]
    return "\n".join(lines)


def write_report(store: Store, reports_dir: str | Path = "reports", now: float | None = None):
    now = now or time.time()
    path = Path(reports_dir) / f"weekly_{time.strftime('%Y-%m-%d', time.localtime(now))}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_report(store, now), encoding="utf-8")
    return path
