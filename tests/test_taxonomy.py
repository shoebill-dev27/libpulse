"""Tests for the CI failure taxonomy. Network-free; pure classification + synthetic results."""

from libpulse import taxonomy


def test_classify_import_error():
    assert (
        taxonomy.classify_failure("ModuleNotFoundError: No module named 'scipy'") == "import-error"
    )


def test_classify_removed_api():
    assert (
        taxonomy.classify_failure("AttributeError: module 'numpy' has no attribute 'float'")
        == "removed-api"
    )
    assert (
        taxonomy.classify_failure("ImportError: cannot import name 'foo' from 'pkg'")
        == "removed-api"
    )


def test_classify_signature_change():
    assert (
        taxonomy.classify_failure("TypeError: f() got an unexpected keyword argument 'x'")
        == "signature-change"
    )
    assert (
        taxonomy.classify_failure("TypeError: f() takes 2 positional arguments but 3 were given")
        == "signature-change"
    )


def test_classify_behavior_change():
    assert taxonomy.classify_failure("AssertionError: assert 3 == 4") == "behavior-change"
    # A generic TypeError that is not a signature mismatch is behavioral.
    assert taxonomy.classify_failure("TypeError: unsupported operand type(s)") == "behavior-change"


def test_classify_deprecation_and_syntax_and_unknown():
    assert taxonomy.classify_failure("DeprecationWarning: x is deprecated") == "deprecation"
    assert taxonomy.classify_failure("SyntaxError: invalid syntax") == "syntax-error"
    assert taxonomy.classify_failure("") == "unknown"
    assert taxonomy.classify_failure("something weird happened") == "unknown"


def _verified(package, case_id, stderr):
    return {
        "package": package,
        "case_id": case_id,
        "verdict": "verified",
        "steps": [
            {"step": "before_on_old", "passed": True, "stderr": ""},
            {"step": "before_on_new", "passed": False, "stderr": stderr},
            {"step": "after_on_new", "passed": True, "stderr": ""},
        ],
    }


def test_taxonomy_from_results_counts_and_examples():
    results = [
        _verified("numpy", "c1", "AttributeError: module 'numpy' has no attribute 'float'"),
        _verified("pandas", "c2", "TypeError: f() got an unexpected keyword argument 'x'"),
        _verified("requests", "c3", "AssertionError: assert 1 == 2"),
        # not verified -> ignored
        {"package": "x", "case_id": "c4", "verdict": "not_breaking", "steps": []},
    ]
    tax = taxonomy.taxonomy_from_results(results)
    assert tax["classified"] == 3
    assert tax["counts"] == {
        "removed-api": 1,
        "signature-change": 1,
        "behavior-change": 1,
    }
    labels = {e["package"]: e["label"] for e in tax["examples"]}
    assert labels == {
        "numpy": "removed-api",
        "pandas": "signature-change",
        "requests": "behavior-change",
    }
    # evidence is the exception summary line
    assert any("has no attribute" in e["evidence"] for e in tax["examples"])


def test_taxonomy_skips_when_breaking_step_absent_or_passed():
    # before_on_new passed (shouldn't happen for verified, but must not crash)
    results = [
        {
            "package": "x",
            "case_id": "c",
            "verdict": "verified",
            "steps": [{"step": "before_on_new", "passed": True, "stderr": ""}],
        }
    ]
    tax = taxonomy.taxonomy_from_results(results)
    assert tax["classified"] == 0
    assert tax["counts"] == {}


def test_summary_line_and_markdown():
    results = [
        _verified("numpy", "c1", "AttributeError: module 'numpy' has no attribute 'float'"),
        _verified("scipy", "c2", "AttributeError: module 'scipy' has no attribute 'bar'"),
    ]
    tax = taxonomy.taxonomy_from_results(results)
    line = taxonomy.summary_line(tax)
    assert "removed-api (2)" in line
    md = taxonomy.render_markdown(tax)
    assert "CI failure taxonomy" in md
    assert "| removed-api | 2 |" in md

    empty = taxonomy.taxonomy_from_results([])
    assert "no classified verified cases" in taxonomy.summary_line(empty)
