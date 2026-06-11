"""Tests for historical_pairs (backfill release-pair derivation). No network."""

import time

from libpulse.watcher import _is_significant_bump, historical_pairs

NOW = time.mktime((2026, 6, 11, 0, 0, 0, 0, 0, 0))


def _data(releases: dict[str, str]) -> dict:
    return {
        "releases": {
            v: [{"upload_time_iso_8601": at}] if at else [{}] for v, at in releases.items()
        }
    }


def test_significant_bump():
    assert _is_significant_bump("1.2.3", "1.3.0")
    assert _is_significant_bump("1.9.0", "2.0.0")
    assert not _is_significant_bump("1.2.3", "1.2.4")


def test_pairs_window_and_patch_filter():
    data = _data(
        {
            "1.0.0": "2024-01-01T00:00:00Z",  # out of window
            "1.1.0": "2025-09-01T00:00:00Z",  # in window; pairs with out-of-window 1.0.0
            "1.1.1": "2025-10-01T00:00:00Z",  # patch bump: filtered by default
            "2.0.0": "2026-01-01T00:00:00Z",
            "2.0.0rc1": "2025-12-01T00:00:00Z",  # non-final: ignored entirely
        }
    )
    pairs = historical_pairs("demo", data, months=12, now=NOW)
    assert [(p.prev_version, p.new_version) for p in pairs] == [
        ("1.1.1", "2.0.0"),  # newest first; prev is the actual predecessor incl. patches
        ("1.0.0", "1.1.0"),
    ]
    assert all(p.package == "demo" for p in pairs)

    with_patch = historical_pairs("demo", data, months=12, now=NOW, include_patch=True)
    assert len(with_patch) == 3


def test_pairs_skip_missing_upload_time():
    data = _data({"1.0.0": "2026-01-01T00:00:00Z", "1.1.0": ""})
    assert historical_pairs("demo", data, months=12, now=NOW) == []
