"""Weekly report tests against a synthetic store."""

import time
from datetime import datetime, timezone

from libpulse.models import MigrationCase, StepResult, Verdict, VerificationResult
from libpulse.report import build_report
from libpulse.store import Store

NOW = time.time()


def _seed(store: Store, package: str, verdict: Verdict, verified_at: float, n: int = 1):
    for i in range(n):
        # Title must be unique per seeded case: case_id is a hash over it.
        case = MigrationCase(package, "1.0.0", "2.0.0", f"{package} {verdict.value} {i}", "b", "a")
        store.upsert_case(case)
        store.save_result(
            VerificationResult(
                case_id=case.case_id,
                verdict=verdict,
                steps=[StepResult("before_on_old", True, 0, "", "")],
                verified_at=verified_at,
            )
        )


def test_build_report(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    _seed(store, "numpy", Verdict.VERIFIED, NOW - 86400, n=2)  # this week
    _seed(store, "numpy", Verdict.NOT_BREAKING, NOW - 30 * 86400)
    _seed(store, "django", Verdict.UNVERIFIABLE, NOW - 86400, n=3)  # 0 verified, flagged

    report = build_report(store, now=NOW)
    assert "**2 verified** cases (+2 in the last 7 days)" in report
    assert "| numpy | 2 | 3 | 0 |" in report
    assert "django" in report.split("## Attention")[1]  # flagged: >=3 judged, 0 verified


def test_report_empty_store(tmp_path):
    report = build_report(Store(tmp_path / "db.sqlite"), now=NOW)
    assert "**0 verified**" in report
    assert "No packages flagged" in report


def test_freshness_lag_reported(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    base = datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp()
    # Two verified cases released the same day, verified 2 and 4 days later.
    for i, lag_days in enumerate((2, 4)):
        case = MigrationCase(
            "numpy",
            "1.0.0",
            "2.0.0",
            f"case {i}",
            "b",
            "a",
            released_at="2024-01-01T00:00:00+00:00",
        )
        store.upsert_case(case)
        store.save_result(
            VerificationResult(
                case_id=case.case_id, verdict=Verdict.VERIFIED, verified_at=base + lag_days * 86400
            )
        )
    report = build_report(store, now=NOW)
    assert (
        "- Freshness lag (release→verified): median 3d, max 4d, "
        "over 2 timestamped verified case(s)." in report
    )


def test_freshness_lag_absent_without_timestamps(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    _seed(store, "numpy", Verdict.VERIFIED, NOW - 86400)  # no released_at
    report = build_report(store, now=NOW)
    assert "- Freshness lag: no timestamped verified cases yet." in report
