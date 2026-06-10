import json

from libpulse.models import MigrationCase, Verdict, VerificationResult


def make_case(**overrides):
    base = dict(
        package="numpy",
        old_version="1.26.4",
        new_version="2.0.2",
        title="np.float_ removed",
        before_snippet="import numpy as np\nassert np.float_(1.5) == 1.5\n",
        after_snippet="import numpy as np\nassert np.float64(1.5) == 1.5\n",
    )
    base.update(overrides)
    return MigrationCase(**base)


def test_case_id_is_stable_and_content_addressed():
    a, b = make_case(), make_case()
    assert a.case_id == b.case_id
    assert a.case_id != make_case(title="other change").case_id


def test_roundtrip_dict():
    case = make_case(extra_requires=["setuptools"], source="https://example.com")
    again = MigrationCase.from_dict(case.to_dict())
    assert again == case


def test_from_dict_ignores_unknown_keys():
    d = make_case().to_dict()
    d["unknown_future_field"] = 123
    assert MigrationCase.from_dict(d).package == "numpy"


def test_result_serializes_verdict_as_string():
    result = VerificationResult(case_id="abc", verdict=Verdict.VERIFIED)
    assert json.loads(json.dumps(result.to_dict()))["verdict"] == "verified"
