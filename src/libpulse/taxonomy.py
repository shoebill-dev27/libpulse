"""CI failure taxonomy: classify *how* a breaking change manifests.

For every VERIFIED case the verifier has already proven that the `before`
snippet fails on the new version (that is what makes the change breaking). This
module reads the stderr of that `before_on_new` step and labels the failure
kind — import-error, removed-api, signature-change, behavior-change,
deprecation, syntax-error, env-error, or unknown. Aggregated over the corpus it
answers "what *kinds* of breakages actually happen in the Python ecosystem,"
which is a teaching/eval signal the corpus itself does not carry (the exported
corpus keeps snippets and verdicts, not tracebacks).

Stdlib-only and offline: classification is pure string matching on tracebacks,
and the aggregation reads the local store. No network.
"""

from __future__ import annotations

import json
import re

# The verifier step whose failure proves a VERIFIED case is breaking.
BREAKING_STEP = "before_on_new"

LABELS = (
    "import-error",
    "removed-api",
    "signature-change",
    "behavior-change",
    "deprecation",
    "syntax-error",
    "env-error",
    "unknown",
)

_SIG_PATTERNS = (
    "unexpected keyword argument",
    "positional argument",
    "takes no arguments",
    "missing 1 required",
    "got multiple values for",
)
_SIG_RE = re.compile(r"takes \d+ positional argument")


def classify_failure(stderr: str) -> str:
    """Label a Python failure from its stderr/traceback. Checked most-specific first."""
    s = stderr or ""
    if "SyntaxError" in s or "IndentationError" in s:
        return "syntax-error"
    if "ModuleNotFoundError" in s or "No module named" in s:
        return "import-error"
    if "cannot import name" in s or "has no attribute" in s:
        # An import or attribute that used to exist and was removed/renamed.
        return "removed-api"
    if any(p in s for p in _SIG_PATTERNS) or _SIG_RE.search(s):
        return "signature-change"
    if "DeprecationWarning" in s or "FutureWarning" in s or "PendingDeprecationWarning" in s:
        return "deprecation"
    if "AssertionError" in s:
        return "behavior-change"
    if "No matching distribution" in s or "Could not find a version" in s:
        return "env-error"
    # Generic value/type errors that are not signature mismatches are behavioral.
    if "TypeError" in s or "ValueError" in s or "KeyError" in s or "RuntimeError" in s:
        return "behavior-change"
    return "unknown"


def _breaking_stderr(steps: list[dict]) -> str | None:
    """Return the stderr of the failing breaking step, or None if not present/failed."""
    for step in steps:
        if step.get("step") == BREAKING_STEP and not step.get("passed", True):
            return step.get("stderr", "")
    return None


def taxonomy_from_results(results: list[dict]) -> dict:
    """Classify a list of result dicts.

    Each result: {"package": str, "case_id": str, "verdict": str, "steps": [StepResult...]}.
    Only VERIFIED results with a failing breaking step are classified.
    """
    counts: dict[str, int] = {label: 0 for label in LABELS}
    examples: list[dict] = []
    classified = 0
    for res in results:
        if res.get("verdict") != "verified":
            continue
        stderr = _breaking_stderr(res.get("steps", []))
        if stderr is None:
            continue
        label = classify_failure(stderr)
        counts[label] += 1
        classified += 1
        examples.append(
            {
                "package": res.get("package", ""),
                "case_id": res.get("case_id", ""),
                "label": label,
                "evidence": _first_error_line(stderr),
            }
        )
    return {
        "classified": classified,
        "counts": {k: v for k, v in counts.items() if v},
        "examples": examples,
    }


def _first_error_line(stderr: str) -> str:
    """The last non-empty traceback line — usually the exception summary."""
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def build_taxonomy(store) -> dict:
    """Build the taxonomy from the local store's verified results."""
    rows = store.conn.execute("""SELECT c.package, r.case_id, r.verdict, r.steps_json
           FROM results r JOIN cases c USING(case_id)
           WHERE r.verdict='verified'""").fetchall()
    results = []
    for row in rows:
        try:
            steps = json.loads(row["steps_json"])
        except (json.JSONDecodeError, TypeError):
            steps = []
        results.append(
            {
                "package": row["package"],
                "case_id": row["case_id"],
                "verdict": row["verdict"],
                "steps": steps,
            }
        )
    return taxonomy_from_results(results)


def summary_line(taxonomy: dict) -> str:
    """One-line report summary: total + dominant failure kind."""
    if not taxonomy["classified"]:
        return "- Failure taxonomy: no classified verified cases yet."
    top_label, top_count = max(taxonomy["counts"].items(), key=lambda kv: kv[1])
    return (
        f"- Failure taxonomy: {taxonomy['classified']} verified case(s) classified; "
        f"most common = {top_label} ({top_count}). Run `libpulse failure-taxonomy`."
    )


def render_markdown(taxonomy: dict) -> str:
    lines = [
        f"# LibPulse CI failure taxonomy — {taxonomy['classified']} verified case(s)",
        "",
        "How each verified breaking change manifests (from the `before_on_new` step).",
        "",
        "| failure kind | count |",
        "|---|---|",
    ]
    for label, count in sorted(taxonomy["counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {label} | {count} |")
    lines += ["", "## Examples", ""]
    for ex in taxonomy["examples"]:
        evidence = ex["evidence"].replace("|", "\\|")
        lines.append(f"- **{ex['package']}** ({ex['label']}): {evidence}")
    lines.append("")
    return "\n".join(lines)
