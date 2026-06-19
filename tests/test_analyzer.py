"""Analyzer unit tests: no network, no API key. HTTP and PyPI fetch are stubbed."""

import json

from libpulse.analyzer import (
    API_URL,
    Analyzer,
    _changelog_to_text,
    _changelog_url_from_pypi,
    _extract_version_section,
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


# --- T12a: changelog deep-fetch ---


def _pypi_with_changelog(package: str) -> dict:
    # No GitHub repo: forces the deep-fetch path to be the only source of notes.
    return {
        "info": {
            "summary": "demo package",
            "project_urls": {"Changelog": "https://demo.example/CHANGELOG.md"},
        }
    }


def test_changelog_url_from_pypi_matches_labels():
    urls = {"Documentation": "https://d", "Release Notes": "https://r/notes"}
    assert _changelog_url_from_pypi({"project_urls": urls}) == "https://r/notes"
    assert _changelog_url_from_pypi({"project_urls": {"Source": "https://s"}}) is None


def test_extract_version_section_isolates_block():
    text = (
        "# Changelog\n"
        "## 2.0.0\n"
        "- Removed foo(); use bar()\n"
        "- Dropped Python 3.8\n"
        "## 1.9.0\n"
        "- Added baz()\n"
    )
    section = _extract_version_section(text, "2.0.0")
    assert "Removed foo()" in section
    assert "Dropped Python 3.8" in section
    assert "Added baz()" not in section  # stopped at the 1.9.0 heading


def test_extract_version_section_falls_back_to_head():
    text = "## 3.1.0\n- newest entry\n## 3.0.0\n- older entry\n"
    # 9.9.9 absent -> return the head (newest entries) rather than nothing.
    assert "newest entry" in _extract_version_section(text, "9.9.9")


def test_changelog_to_text_strips_html_but_keeps_markdown():
    html = (
        "<html><head><style>x{}</style></head><body><h2>2.0.0</h2><p>Removed foo</p></body></html>"
    )
    text = _changelog_to_text("https://demo.example/changelog", html)
    assert "Removed foo" in text
    assert "x{}" not in text  # style content dropped
    md = "## 2.0.0\n- Removed foo\n"
    assert _changelog_to_text("https://demo.example/CHANGELOG.md", md) == md


def test_fetch_context_deep_fetches_changelog_when_no_release_notes():
    fetched = []

    def text_fetch(url):
        fetched.append(url)
        return "# Changelog\n## 2.0.0\n- Removed demo.foo(); use demo.bar()\n## 1.0.0\n- init\n"

    def http(url, headers, payload=None, timeout=0):
        raise AssertionError("no GitHub repo, so the releases API must not be called")

    analyzer = Analyzer(
        api_key="k", http=http, pypi_fetch=_pypi_with_changelog, text_fetch=text_fetch
    )
    context = analyzer.fetch_context(REL)
    assert fetched == ["https://demo.example/CHANGELOG.md"]
    assert "Removed demo.foo()" in context
    assert "- init" not in context  # only the 2.0.0 section


def test_deep_fetch_skipped_when_github_notes_present():
    def text_fetch(url):
        raise AssertionError("changelog must not be fetched when release notes exist")

    def http(url, headers, payload=None, timeout=0):
        return [{"tag_name": "v2.0.0", "body": "Removed foo(); use bar()."}]

    analyzer = Analyzer(api_key="k", http=http, pypi_fetch=_pypi_stub, text_fetch=text_fetch)
    assert "Removed foo()" in analyzer.fetch_context(REL)


def test_deep_fetch_error_degrades_gracefully(capsys):
    def text_fetch(url):
        raise OSError("changelog host down")

    analyzer = Analyzer(
        api_key="k",
        http=lambda *a, **k: (_ for _ in ()).throw(OSError("no gh")),
        pypi_fetch=_pypi_with_changelog,
        text_fetch=text_fetch,
    )
    context = analyzer.fetch_context(REL)
    assert "PyPI summary: demo package" in context  # still returns what it has
    assert "changelog fetch error" in capsys.readouterr().err


def test_escalates_to_fallback_model_on_significant_bump(tmp_path):
    models_called = []

    def http(url, headers, payload=None, timeout=0):
        if url != API_URL:
            return []
        models_called.append(payload["model"])
        if len(models_called) == 1:
            return _llm_response([])  # cheap model finds nothing
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

    analyzer = Analyzer(
        api_key="k",
        model="cheap-model",
        fallback_model="strong-model",
        http=http,
        pypi_fetch=_pypi_stub,
    )
    written = analyzer.analyze(REL, tmp_path / "cases")  # 1.0.0 -> 2.0.0: major bump
    assert models_called == ["cheap-model", "strong-model"]
    assert len(written) == 1


def test_no_escalation_on_patch_bump_or_when_disabled(tmp_path):
    calls = []

    def http(url, headers, payload=None, timeout=0):
        if url != API_URL:
            return []
        calls.append(payload["model"])
        return _llm_response([])

    patch_release = NewRelease("demo", "1.0.0", "1.0.1", "")
    analyzer = Analyzer(
        api_key="k", model="m", fallback_model="strong", http=http, pypi_fetch=_pypi_stub
    )
    assert analyzer.analyze(patch_release, tmp_path / "cases") == []
    assert calls == ["m"]  # patch bump: no retry

    calls.clear()
    same_model = Analyzer(
        api_key="k", model="m", fallback_model="m", http=http, pypi_fetch=_pypi_stub
    )
    assert same_model.analyze(REL, tmp_path / "cases") == []
    assert calls == ["m"]  # fallback == primary: disabled


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
