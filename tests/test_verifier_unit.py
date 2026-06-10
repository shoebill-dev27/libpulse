"""Unit tests for snippet execution; no venv creation (uses current python)."""

import sys

from libpulse.verifier import run_snippet


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
