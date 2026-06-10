"""CLI entry point. The `cycle` command is the unattended loop and must never
crash mid-cycle: per-case failures are recorded and skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .models import MigrationCase, Verdict
from .store import Store
from .verifier import Verifier
from .watcher import NewRelease, default_fetcher, discover_new_releases


def _ingest(store: Store, cases_dir: Path) -> int:
    """Load case JSON files dropped into the queue directory by the analyzer."""
    count = 0
    if not cases_dir.exists():
        return 0
    for path in sorted(cases_dir.glob("*.json")):
        try:
            store.upsert_case(MigrationCase.from_json_file(str(path)))
            count += 1
        except Exception as exc:  # one bad file must not kill the cycle
            print(f"[ingest] skipped {path.name}: {exc}", file=sys.stderr)
    return count


def cmd_verify_case(args: argparse.Namespace) -> int:
    case = MigrationCase.from_json_file(args.case_file)
    result = Verifier().verify(case)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.verdict == Verdict.VERIFIED else 1


def cmd_cycle(args: argparse.Namespace) -> int:
    started = time.time()
    store = Store(args.db)
    ingested = _ingest(store, Path(args.cases_dir))
    verifier = Verifier()
    outcomes: dict[str, str] = {}
    for case_id in store.pending_case_ids():
        case = store.get_case(case_id)
        try:
            result = verifier.verify(case)
        except Exception as exc:  # harness bug: record, continue
            print(f"[cycle] {case.package} {case_id}: harness error {exc}", file=sys.stderr)
            continue
        store.save_result(result)
        outcomes[case_id] = result.verdict.value
        print(
            f"[cycle] {case.package} {case.old_version}->{case.new_version}: {result.verdict.value}"
        )
    written = store.export_corpus(args.corpus_dir)
    summary = {
        "ran_at": int(started),
        "duration_s": round(time.time() - started, 1),
        "ingested": ingested,
        "verified_this_cycle": sum(1 for v in outcomes.values() if v == "verified"),
        "outcomes": outcomes,
        "corpus_files": [str(p) for p in written],
        "totals": store.verdict_counts(),
    }
    reports = Path(args.reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d", time.localtime(started))
    (reports / f"cycle_{stamp}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary["totals"]))
    return 0


def _watch(store: Store, packages_file: Path, fetch=default_fetcher) -> list[NewRelease]:
    """Run release discovery and print one JSON line per new release.

    Returns the discovered releases so cmd_cycle can reuse this later (T10).
    """
    releases = discover_new_releases(store, packages_file, fetch=fetch)
    for release in releases:
        print(json.dumps(release.to_dict()))
    return releases


def cmd_watch(args: argparse.Namespace) -> int:
    store = Store(args.db)
    _watch(store, Path(args.packages_file))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    written = Store(args.db).export_corpus(args.corpus_dir)
    print("\n".join(str(p) for p in written) or "(corpus empty)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="libpulse")
    parser.add_argument("--db", default="data/libpulse.db")
    parser.add_argument("--cases-dir", default="data/cases")
    parser.add_argument("--corpus-dir", default="data/corpus")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--packages-file", default="data/packages.txt")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("verify-case", help="verify a single case JSON file")
    p.add_argument("case_file")
    p.set_defaults(func=cmd_verify_case)

    p = sub.add_parser(
        "cycle", help="unattended loop: ingest queue, verify pending, export, report"
    )
    p.set_defaults(func=cmd_cycle)

    p = sub.add_parser(
        "watch", help="poll PyPI for new final releases of tracked packages (one JSON line each)"
    )
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("export", help="re-export the verified corpus")
    p.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
