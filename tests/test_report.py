"""Weekly report tests against a synthetic store."""

import time

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
