"""End-to-end proof: the harness verifies a real, known breaking change.

numpy 2.0 removed the np.float_ alias (NumPy 2.0 migration guide). This test
builds real venvs and installs both versions; marked integration (slow).
"""

import pytest

from libpulse.models import Verdict
from libpulse.verifier import Verifier, VenvCache
from tests.test_models import make_case


@pytest.mark.integration
def test_numpy_float_alias_removal_verified(tmp_path):
    verifier = Verifier(VenvCache(tmp_path / "venvs"))
    result = verifier.verify(make_case())
    assert result.verdict == Verdict.VERIFIED, result.to_dict()
    steps = {s.step: s.passed for s in result.steps}
    assert steps == {
        "before_on_old": True,
        "before_on_new": False,
        "after_on_new": True,
        "after_on_old": True,
    }
    assert result.after_works_on_old is True


@pytest.mark.integration
def test_false_claim_yields_not_breaking(tmp_path):
    verifier = Verifier(VenvCache(tmp_path / "venvs"))
    false_claim = make_case(
        title="np.mean was removed (false claim)",
        before_snippet="import numpy as np\nassert np.mean([1, 2, 3]) == 2\n",
        after_snippet="import numpy as np\nassert sum([1,2,3])/3 == 2\n",
    )
    result = verifier.verify(false_claim)
    assert result.verdict == Verdict.NOT_BREAKING
