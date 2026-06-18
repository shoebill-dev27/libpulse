"""Tests for the deprecation feed. Network-free: corpus on disk + fake fetcher."""

import json

from libpulse import deprecations


def _write_corpus(tmp_path, package, entries):
    d = tmp_path / "corpus"
    d.mkdir(exist_ok=True)
    (d / f"{package}.json").write_text(
        json.dumps({"package": package, "entries": entries}), encoding="utf-8"
    )
    return str(d)


def test_scan_text_extracts_api_versions_and_message():
    text = "The `np.float` alias is deprecated in 1.20 and removed in 2.0."
    records = deprecations._scan_text(text, "numpy", "corpus", "2024-01-01")
    assert len(records) == 1
    r = records[0]
    assert r.api == "np.float"
    assert r.deprecated_in == "1.20"
    assert r.removed_in == "2.0"
    assert r.package == "numpy"
    assert r.released_at == "2024-01-01"


def test_from_corpus_scans_title_and_snippets(tmp_path):
    entries = [
        {
            "title": "np.bool removed",
            "before": "x = np.bool  # DeprecationWarning: deprecated in 1.20",
            "after": "x = bool",
            "source": "https://example.com/notes",
            "released_at": "2024-02-01",
        }
    ]
    corpus_dir = _write_corpus(tmp_path, "numpy", entries)
    records = deprecations.from_corpus(["numpy"], corpus_dir)
    assert any("deprecated in 1.20" in r.message for r in records)
    assert all(r.package == "numpy" for r in records)


def test_from_pypi_uses_injected_fetcher():
    def fake_fetch(package):
        return {
            "info": {
                "summary": "",
                "description": "Note: foo() is scheduled for removal in 3.0.",
            }
        }

    records = deprecations.from_pypi(["pkg"], fetch=fake_fetch)
    assert len(records) == 1
    assert records[0].removed_in == "3.0"
    assert records[0].source == "pypi"


def test_from_pypi_swallows_fetch_errors():
    def boom(package):
        raise RuntimeError("network down")

    assert deprecations.from_pypi(["pkg"], fetch=boom) == []


def test_build_feed_dedupes_and_orders_newest_first(tmp_path):
    entries = [
        {
            "title": "a deprecated in 1.0",
            "before": "",
            "after": "",
            "source": "corpus",
            "released_at": "2023-01-01",
        },
        {
            "title": "b deprecated in 2.0",
            "before": "",
            "after": "",
            "source": "corpus",
            "released_at": "2025-01-01",
        },
    ]
    corpus_dir = _write_corpus(tmp_path, "pkg", entries)

    def fake_fetch(package):
        # Duplicate of the first corpus message must be de-duped.
        return {"info": {"summary": "", "description": "a deprecated in 1.0"}}

    feed = deprecations.build_feed("pkg".split(), corpus_dir=corpus_dir, fetch=fake_fetch)
    # newest-first by released_at; corpus dupes collapse but pypi (no date) stays once
    assert feed[0].released_at == "2025-01-01"
    messages = [r.message for r in feed]
    assert messages.count("a deprecated in 1.0") == 1


def test_render_markdown_has_table_header():
    md = deprecations.render_markdown([])
    assert "| package | api |" in md
    assert "0 signal(s)" in md
