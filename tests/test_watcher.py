"""Watcher tests: all use injected fake fetchers — no network."""

from __future__ import annotations

from libpulse.store import Store
from libpulse.watcher import (
    NewRelease,
    discover_new_releases,
    is_final_version,
    read_packages,
)


def make_data(*versions: str) -> dict:
    """Build a minimal PyPI-shaped JSON dict from version strings.

    Each version gets one file with an upload time derived from the version so
    times sort consistently with version order.
    """
    releases = {}
    for i, v in enumerate(versions):
        releases[v] = [{"upload_time_iso_8601": f"2024-01-{i + 1:02d}T00:00:00Z"}]
    return {"releases": releases}


def fetcher_for(mapping: dict[str, dict]):
    def fetch(package: str) -> dict:
        return mapping[package]

    return fetch


def write_packages(tmp_path, *names: str):
    path = tmp_path / "packages.txt"
    path.write_text("# header\n" + "\n".join(names) + "\n", encoding="utf-8")
    return path


def test_read_packages_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "p.txt"
    path.write_text("# c\nnumpy\n\n  pandas  # inline\nflask\n", encoding="utf-8")
    assert read_packages(path) == ["numpy", "pandas", "flask"]


def test_is_final_version_filters_prereleases():
    assert is_final_version("1.2.3")
    assert is_final_version("2")
    assert not is_final_version("1.0.0rc1")
    assert not is_final_version("1.0.0.dev1")
    assert not is_final_version("1.0.0b2")
    assert not is_final_version("1.0.0.post1")
    assert not is_final_version("1.0.0+local")


def test_first_run_no_flood_reports_single_latest_pair(tmp_path):
    store = Store(tmp_path / "t.db")
    pkgs = write_packages(tmp_path, "numpy")
    fetch = fetcher_for({"numpy": make_data("1.0.0", "1.1.0", "2.0.0")})

    found = discover_new_releases(store, pkgs, fetch=fetch)

    assert found == [NewRelease("numpy", "1.1.0", "2.0.0", "2024-01-03T00:00:00Z")]
    assert store.get_watermark("numpy") == "2.0.0"


def test_first_run_single_version_has_empty_prev(tmp_path):
    store = Store(tmp_path / "t.db")
    pkgs = write_packages(tmp_path, "numpy")
    fetch = fetcher_for({"numpy": make_data("1.0.0")})

    found = discover_new_releases(store, pkgs, fetch=fetch)

    assert found == [NewRelease("numpy", "", "1.0.0", "2024-01-01T00:00:00Z")]
    assert store.get_watermark("numpy") == "1.0.0"


def test_new_versions_above_watermark_detected(tmp_path):
    store = Store(tmp_path / "t.db")
    store.set_watermark("numpy", "1.1.0")
    pkgs = write_packages(tmp_path, "numpy")
    fetch = fetcher_for({"numpy": make_data("1.0.0", "1.1.0", "1.2.0", "2.0.0")})

    found = discover_new_releases(store, pkgs, fetch=fetch)

    assert [(r.prev_version, r.new_version) for r in found] == [
        ("1.1.0", "1.2.0"),
        ("1.2.0", "2.0.0"),
    ]
    assert store.get_watermark("numpy") == "2.0.0"


def test_no_new_versions_returns_nothing(tmp_path):
    store = Store(tmp_path / "t.db")
    store.set_watermark("numpy", "2.0.0")
    pkgs = write_packages(tmp_path, "numpy")
    fetch = fetcher_for({"numpy": make_data("1.0.0", "2.0.0")})

    assert discover_new_releases(store, pkgs, fetch=fetch) == []
    assert store.get_watermark("numpy") == "2.0.0"


def test_prereleases_are_filtered_from_detection(tmp_path):
    store = Store(tmp_path / "t.db")
    store.set_watermark("numpy", "1.0.0")
    pkgs = write_packages(tmp_path, "numpy")
    # 2.0.0rc1 and 1.5.0.dev0 must be ignored; only final 1.5.0 / 2.0.0 count.
    fetch = fetcher_for({"numpy": make_data("1.0.0", "1.5.0.dev0", "1.5.0", "2.0.0rc1", "2.0.0")})

    found = discover_new_releases(store, pkgs, fetch=fetch)

    assert [r.new_version for r in found] == ["1.5.0", "2.0.0"]
    assert store.get_watermark("numpy") == "2.0.0"


def test_malformed_response_is_skipped(tmp_path):
    store = Store(tmp_path / "t.db")
    pkgs = write_packages(tmp_path, "broken", "numpy")
    fetch = fetcher_for({"broken": {"no_releases_key": True}, "numpy": make_data("1.0.0", "2.0.0")})

    found = discover_new_releases(store, pkgs, fetch=fetch)

    # broken is skipped (no crash, no watermark); numpy still processed.
    assert [r.package for r in found] == ["numpy"]
    assert store.get_watermark("broken") is None
    assert store.get_watermark("numpy") == "2.0.0"


def test_watermark_persists_across_calls(tmp_path):
    store = Store(tmp_path / "t.db")
    pkgs = write_packages(tmp_path, "numpy")
    mapping = {"numpy": make_data("1.0.0", "1.1.0")}
    fetch = fetcher_for(mapping)

    first = discover_new_releases(store, pkgs, fetch=fetch)
    assert [r.new_version for r in first] == ["1.1.0"]

    # Second call with the same data: nothing new.
    assert discover_new_releases(store, pkgs, fetch=fetch) == []

    # A new release appears: detected relative to persisted watermark.
    mapping["numpy"] = make_data("1.0.0", "1.1.0", "1.2.0")
    third = discover_new_releases(store, pkgs, fetch=fetch)
    assert [(r.prev_version, r.new_version) for r in third] == [("1.1.0", "1.2.0")]
