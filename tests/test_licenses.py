"""Tests for the license matrix. Network-free: fake fetcher with canned metadata."""

from libpulse import licenses


def test_normalize_license_from_string_and_classifiers():
    assert licenses.normalize_license({"license": "MIT License"}) == "MIT"
    assert (
        licenses.normalize_license(
            {"license": "", "classifiers": ["License :: OSI Approved :: Apache Software License"]}
        )
        == "Apache-2.0"
    )
    assert (
        licenses.normalize_license(
            {"classifiers": ["License :: OSI Approved :: GNU General Public License v3 (GPLv3)"]}
        )
        == "GPL"
    )
    assert licenses.normalize_license({"license": "Weird Custom 1.0"}) == "UNKNOWN"


def test_direct_dependencies_parses_names_and_skips_extras():
    info = {
        "requires_dist": [
            "numpy>=1.20",
            "requests (>=2.0)",
            "pytest>=7.0; extra == 'dev'",
            "rich; extra == 'cli'",
        ]
    }
    assert licenses.direct_dependencies(info) == ["numpy", "requests"]


def test_build_matrix_flags_permissive_with_copyleft_dependency():
    db = {
        "app": {"info": {"license": "MIT", "requires_dist": ["copyleftlib>=1.0", "safelib"]}},
        "copyleftlib": {"info": {"license": "GPLv3", "requires_dist": []}},
        "safelib": {"info": {"license": "BSD", "requires_dist": []}},
    }

    def fake_fetch(package):
        return db[package]

    matrix = licenses.build_matrix(["app"], fetch=fake_fetch)
    row = matrix["packages"][0]
    assert row["license"] == "MIT"
    assert row["copyleft_conflict"] is True
    assert {d["name"]: d["license"] for d in row["dependencies"]} == {
        "copyleftlib": "GPL",
        "safelib": "BSD",
    }
    assert matrix["conflicts"] == 1


def test_build_matrix_no_conflict_when_package_is_copyleft():
    db = {
        "gplapp": {"info": {"license": "GPLv3", "requires_dist": ["gpldep"]}},
        "gpldep": {"info": {"license": "AGPL", "requires_dist": []}},
    }
    matrix = licenses.build_matrix(["gplapp"], fetch=lambda p: db[p])
    assert matrix["packages"][0]["copyleft_conflict"] is False
    assert matrix["conflicts"] == 0


def test_build_matrix_skips_unfetchable_package():
    def boom(package):
        raise RuntimeError("down")

    matrix = licenses.build_matrix(["x"], fetch=boom)
    assert matrix["packages"] == []


def test_render_markdown_marks_conflicts():
    db = {
        "app": {"info": {"license": "MIT", "requires_dist": ["gpllib"]}},
        "gpllib": {"info": {"license": "GPL", "requires_dist": []}},
    }
    matrix = licenses.build_matrix(["app"], fetch=lambda p: db[p])
    md = licenses.render_markdown(matrix)
    assert "copyleft conflict" in md
    assert "yes" in md
