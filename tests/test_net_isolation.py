"""T14a: snippets must run without network access where unshare is usable."""

import sys

import pytest

from libpulse.verifier import _isolation_prefix, run_snippet

NET_CODE = """
import urllib.request
urllib.request.urlopen("https://pypi.org", timeout=3)
"""


@pytest.mark.skipif(not _isolation_prefix(), reason="unshare -rn not usable here")
def test_network_blocked_for_snippets():
    passed, _, _, stderr = run_snippet(sys.executable, NET_CODE, timeout=15)
    assert not passed
    assert "URLError" in stderr or "OSError" in stderr or "urlopen" in stderr


def test_plain_snippets_still_pass():
    passed, rc, _, _ = run_snippet(sys.executable, "assert 1 + 1 == 2\n")
    assert passed and rc == 0
