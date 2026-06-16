import json

from libpulse.models import StepResult, Verdict, VerificationResult
from libpulse.store import Store
from tests.test_models import make_case


def test_upsert_fetch_roundtrip(tmp_path):
    store = Store(tmp_path / "t.db")
    case = make_case(extra_requires=["six"])
    store.upsert_case(case)
    assert store.get_case(case.case_id) == case
    assert store.pending_case_ids() == [case.case_id]


def test_released_at_roundtrips(tmp_path):
    store = Store(tmp_path / "t.db")
    case = make_case(released_at="2024-05-01T12:00:00Z")
    store.upsert_case(case)
    fetched = store.get_case(case.case_id)
    assert fetched == case
    assert fetched.released_at == "2024-05-01T12:00:00Z"


def test_export_includes_released_at(tmp_path):
    store = Store(tmp_path / "t.db")
    case = make_case(released_at="2024-05-01T12:00:00Z")
    store.upsert_case(case)
    store.save_result(VerificationResult(case.case_id, Verdict.VERIFIED))
    files = store.export_corpus(tmp_path / "corpus")
    entry = json.loads(files[0].read_text())["entries"][0]
    assert entry["released_at"] == "2024-05-01T12:00:00Z"


def test_result_clears_pending_and_counts(tmp_path):
    store = Store(tmp_path / "t.db")
    case = make_case()
    store.upsert_case(case)
    store.save_result(
        VerificationResult(
            case.case_id,
            Verdict.VERIFIED,
            steps=[StepResult("before_on_old", True, 0, "", "")],
            after_works_on_old=True,
        )
    )
    assert store.pending_case_ids() == []
    assert store.verdict_counts() == {"verified": 1}


def test_export_only_verified(tmp_path):
    store = Store(tmp_path / "t.db")
    good, bad = make_case(), make_case(title="claims something false")
    store.upsert_case(good)
    store.upsert_case(bad)
    store.save_result(VerificationResult(good.case_id, Verdict.VERIFIED))
    store.save_result(VerificationResult(bad.case_id, Verdict.NOT_BREAKING))
    files = store.export_corpus(tmp_path / "corpus")
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert [e["case_id"] for e in data["entries"]] == [good.case_id]
    assert data["entries"][0]["verdict"] == "verified"
