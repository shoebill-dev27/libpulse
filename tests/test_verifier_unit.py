"""Unit tests for snippet execution; no venv creation (uses current python)."""

import sys

import pytest

from libpulse.verifier import EnvSetupError, VenvCache, run_snippet


def test_python_candidates_start_with_current():
    cands = VenvCache._python_candidates()
    assert cands[0][0] == sys.executable
    current = sys.version_info[:2]
    assert cands[0][1] == f"{current[0]}.{current[1]}"
    # Fallbacks, if any, must be strictly newer than the running interpreter.
    for _, tag in cands[1:]:
        major, minor = (int(p) for p in tag.split("."))
        assert (major, minor) > current


@pytest.mark.parametrize(
    "msg, should_retry",
    [
        # uv's wording when a package ships no wheel for the running interpreter
        # under --no-build. This one froze the corpus for ~3 months: the newer
        # interpreter has the wheel, but the ladder gave up before trying it.
        ("Because numpy==2.5.0 has no usable wheels and ...", True),
        ("The Python version does not satisfy Python>=3.12", True),
        ("package requires Python >=3.12", True),
        # Genuine failures must still be final, not retried on every interpreter.
        ("No solution found: package==1.0 was not found in the registry", False),
    ],
)
def test_env_build_retries_only_on_interpreter_fit(monkeypatch, tmp_path, msg, should_retry):
    cache = VenvCache(root=tmp_path)
    monkeypatch.setattr(
        VenvCache,
        "_python_candidates",
        staticmethod(lambda: [("py-old", "3.11"), ("py-new", "3.12")]),
    )
    tried: list[str] = []

    def fake_build(self, base_python, tag, specs):
        tried.append(base_python)
        raise EnvSetupError(msg)

    monkeypatch.setattr(VenvCache, "_build", fake_build)
    with pytest.raises(EnvSetupError):
        cache.python_for(["numpy==2.5.0"])
    assert tried == (["py-old", "py-new"] if should_retry else ["py-old"])


def test_passing_snippet():
    passed, rc, out, err = run_snippet(sys.executable, "print('ok')")
    assert passed and rc == 0
    assert "ok" in out


def test_failing_snippet():
    passed, rc, _, err = run_snippet(sys.executable, "raise RuntimeError('boom')")
    assert not passed and rc != 0
    assert "boom" in err


def test_snippet_env_is_scrubbed():
    code = "import os\nassert 'ANTHROPIC_API_KEY' not in os.environ\nassert 'AWS_SECRET_ACCESS_KEY' not in os.environ\n"
    passed, _, _, err = run_snippet(sys.executable, code)
    assert passed, err


def test_snippet_timeout():
    passed, rc, _, err = run_snippet(sys.executable, "import time\ntime.sleep(5)", timeout=1)
    assert not passed and rc == -1
    assert "timeout" in err
