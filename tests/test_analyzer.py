"""Analyzer unit tests: no network, no API key. HTTP and PyPI fetch are stubbed."""

import json

from libpulse.analyzer import (
    API_URL,
    Analyzer,
    _github_repo_from_pypi,
    _matching_release_notes,
)
from libpulse import cli
from libpulse.watcher import NewRelease

REL = NewRelease("demo", "1.0.0", "2.0.0", "2026-06-01T00:00:00Z")


def _llm_response(cases: list[dict]) -> dict:
    return {"content": [{"type": "text", "text": json.dumps({"cases": cases})}]}


def _pypi_stub(package: str) -> dict:
    return {
        "info": {
            "summary": "demo package",
            "project_urls": {"Source": "https://github.com/acme/demo"},
        }
    }


def test_disabled_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    analyzer = Analyzer()
    assert not analyzer.enabled
    assert analyzer.analyze(REL, tmp_path / "cases") == []
    assert not (tmp_path / "cases").exists()


def test_model_comes_from_env_never_hardcoded(monkeypatch):
    monkeypatch.setenv("LIBPULSE_MODEL", "claude-sonnet-4-6")
    assert Analyzer(api_key="k").model == "claude-sonnet-4-6"
    monkeypatch.delenv("LIBPULSE_MODEL", raising=False)
    assert Analyzer(api_key="k").model == "claude-haiku-4-5"


def test_skips_release_without_prev_version(tmp_path):
    def http(*a, **kw):
        raise AssertionError("must not call the API for an unprovable release")

    analyzer = Analyzer(api_key="k", http=http, pypi_fetch=_pypi_stub)
    release = NewRelease("demo", "", "2.0.0", "")
    assert analyzer.analyze(release, tmp_path / "cases") == []


def test_analyze_writes_case_files_and_request_shape(monkeypatch, tmp_path):
    monkeypatch.delenv("LIBPULSE_MODEL", raising=False)
    calls = []

    def http(url, headers, payload=None, timeout=0):
        calls.append((url, headers, payload))
        if url == API_URL:
            return _llm_response(
                [
                    {
                        "title": "demo.foo removed",
                        "before_snippet": "import demo\ndemo.foo()\n",
                        "after_snippet": "import demo\ndemo.bar()\n",
                        "extra_requires": [],
                    }
                ]
            )
        return [{"tag_name": "v2.0.0", "body": "Removed foo(); use bar()."}]

    analyzer = Analyzer(api_key="test-key", http=http, pypi_fetch=_pypi_stub)
    written = analyzer.analyze(REL, tmp_path / "cases")

    assert len(written) == 1
    data = json.loads(written[0].read_text())
    assert data["package"] == "demo"
    assert data["old_version"] == "1.0.0"
    assert data["new_version"] == "2.0.0"
    assert data["source"] == "pypi:demo==2.0.0"
    assert data["case_id"]  # stable id computed

    url, headers, payload = calls[-1]  # last call is the Messages API POST
    assert url == API_URL
    assert headers["x-api-key"] == "test-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert payload["model"] == "claude-haiku-4-5"
    assert payload["output_config"]["format"]["type"] == "json_schema"
    prompt = payload["messages"][0]["content"]
    assert "Removed foo()" in prompt  # release notes made it into the prompt


def test_context_degrades_when_github_unreachable(tmp_path):
    def http(url, headers, payload=None, timeout=0):
        if url == API_URL:
            return _llm_response([])
        raise OSError("github down")

    analyzer = Analyzer(api_key="k", http=http, pypi_fetch=_pypi_stub)
    assert "PyPI summary: demo package" in analyzer.fetch_context(REL)
    assert analyzer.analyze(REL, tmp_path / "cases") == []  # empty cases, no crash


def test_github_repo_from_pypi():
    info = {"project_urls": {"Homepage": "https://github.com/acme/demo.git"}}
    assert _github_repo_from_pypi(info) == "acme/demo"
    assert _github_repo_from_pypi({"info": {}}) is None


def test_matching_release_notes_prefers_exact_tag():
    releases = [
        {"tag_name": "v3.0.0", "body": "three"},
        {"tag_name": "v2.0.0", "body": "two"},
        {"tag_name": "v1.0.0", "body": "one"},
    ]
    assert _matching_release_notes(releases, "2.0.0") == ["## v2.0.0\ntwo"]
    # No exact match: fall back to the newest bodies.
    assert _matching_release_notes(releases, "9.9.9") == ["## v3.0.0\nthree", "## v2.0.0\ntwo"]


def test_cycle_analyze_catches_per_release_errors(tmp_path, capsys):
    def http(url, headers, payload=None, timeout=0):
        raise RuntimeError("boom")

    analyzer = Analyzer(api_key="k", http=http, pypi_fetch=lambda p: {"info": {}})
    generated = cli._analyze([REL], tmp_path / "cases", analyzer=analyzer)
    assert generated == 0
    assert "boom" in capsys.readouterr().err


def test_cycle_runs_offline_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    packages = tmp_path / "packages.txt"
    packages.write_text("# no packages tracked\n", encoding="utf-8")
    rc = cli.main(
        [
            "--db",
            str(tmp_path / "db.sqlite"),
            "--cases-dir",
            str(tmp_path / "cases"),
            "--corpus-dir",
            str(tmp_path / "corpus"),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--packages-file",
            str(packages),
            "cycle",
        ]
    )
    assert rc == 0
    assert list((tmp_path / "reports").glob("cycle_*.json"))
