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


LOOPBACK_CODE = """
import socket
server = socket.socket()
server.bind(("127.0.0.1", 0))
server.listen(1)
client = socket.socket()
client.settimeout(5)
client.connect(server.getsockname())
conn, _ = server.accept()
conn.sendall(b"ok")
assert client.recv(2) == b"ok"
"""


@pytest.mark.skipif(not _isolation_prefix(), reason="unshare -rn not usable here")
def test_loopback_allowed_under_isolation():
    # Local server fixtures (aiohttp etc.) are legitimate; only external
    # network must be unreachable.
    passed, rc, _, stderr = run_snippet(sys.executable, LOOPBACK_CODE, timeout=15)
    assert passed, stderr


def test_plain_snippets_still_pass():
    passed, rc, _, _ = run_snippet(sys.executable, "assert 1 + 1 == 2\n")
    assert passed and rc == 0
