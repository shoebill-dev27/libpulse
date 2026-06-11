"""Corpus read-side tests (stdlib-only) plus an MCP wiring smoke test."""

import json

import pytest

from libpulse import corpus


def _write_corpus(tmp_path, package, versions):
    entries = [
        {
            "case_id": f"id{i}",
            "package": package,
            "old_version": old,
            "new_version": new,
            "title": f"change {i}",
            "before": "x",
            "after": "y",
            "verdict": "verified",
        }
        for i, (old, new) in enumerate(versions)
    ]
    (tmp_path / f"{package}.json").write_text(
        json.dumps({"package": package, "entries": entries}), encoding="utf-8"
    )
    return entries


def test_list_packages(tmp_path):
    _write_corpus(tmp_path, "numpy", [("1.26.4", "2.0.0"), ("2.0.0", "2.2.0")])
    _write_corpus(tmp_path, "flask", [("2.3.0", "3.0.0")])
    rows = corpus.list_packages(corpus=tmp_path)
    assert rows == [
        {"package": "flask", "cases": 1, "latest_version": "3.0.0"},
        {"package": "numpy", "cases": 2, "latest_version": "2.2.0"},
    ]


def test_list_packages_missing_dir(tmp_path):
    assert corpus.list_packages(corpus=tmp_path / "nope") == []


def test_query_range_filtering(tmp_path):
    _write_corpus(tmp_path, "numpy", [("1.26.4", "2.0.0"), ("2.0.0", "2.2.0"), ("2.2.0", "3.0.0")])
    # Upgrading 2.0.0 -> 2.2.0 crosses only the 2.2.0 change.
    result = corpus.query_migrations("numpy", "2.0.0", "2.2.0", corpus=tmp_path)
    assert [e["new_version"] for e in result["entries"]] == ["2.2.0"]
    assert result["count"] == 1
    # No bounds: everything.
    assert corpus.query_migrations("numpy", corpus=tmp_path)["count"] == 3
    # Non-numeric bound is ignored, not guessed at.
    assert corpus.query_migrations("numpy", "2.0.0rc1", corpus=tmp_path)["count"] == 3


def test_query_unknown_package(tmp_path):
    result = corpus.query_migrations("ghost", corpus=tmp_path)
    assert result == {
        "package": "ghost",
        "from_version": None,
        "to_version": None,
        "count": 0,
        "entries": [],
    }


def test_corpus_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBPULSE_CORPUS_DIR", str(tmp_path))
    assert corpus.corpus_dir() == tmp_path


def test_mcp_server_builds_with_both_tools():
    pytest.importorskip("mcp")
    import anyio

    from libpulse.mcp_server import build_server

    server = build_server()
    tools = anyio.run(server.list_tools)
    assert {t.name for t in tools} == {"list_packages", "query_migrations"}
