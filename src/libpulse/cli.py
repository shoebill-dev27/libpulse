"""CLI entry point. The `cycle` command is the unattended loop and must never
crash mid-cycle: per-case failures are recorded and skipped.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .analyzer import Analyzer
from .models import MigrationCase, Verdict
from .store import Store
from .verifier import Verifier
from .watcher import NewRelease, default_fetcher, discover_new_releases, historical_pairs


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


def _analyze(releases: list[NewRelease], cases_dir: Path, analyzer: Analyzer | None = None) -> int:
    """Run the analyzer over discovered releases; per-release errors are logged & skipped."""
    analyzer = analyzer or Analyzer()
    if not analyzer.enabled:
        if releases:
            print(
                "[analyze] ANTHROPIC_API_KEY not set: skipping case generation "
                f"for {len(releases)} release(s)",
                file=sys.stderr,
            )
        return 0
    generated = 0
    for release in releases:
        try:
            written = analyzer.analyze(release, cases_dir)
        except Exception as exc:  # one bad release must not kill the cycle
            print(
                f"[analyze] {release.package} {release.new_version}: error: {exc}",
                file=sys.stderr,
            )
            continue
        generated += len(written)
        print(f"[analyze] {release.package} {release.new_version}: {len(written)} candidate(s)")
    return generated


def cmd_cycle(args: argparse.Namespace) -> int:
    started = time.time()
    store = Store(args.db)
    try:
        releases = _watch(store, Path(args.packages_file))
    except Exception as exc:  # watch failure must not kill the cycle
        print(f"[cycle] watch error: {exc}", file=sys.stderr)
        releases = []
    generated = _analyze(releases, Path(args.cases_dir))
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
        "releases_found": len(releases),
        "cases_generated": generated,
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


def cmd_analyze(args: argparse.Namespace) -> int:
    analyzer = Analyzer()
    if not analyzer.enabled:
        print("ANTHROPIC_API_KEY not set; analyzer is disabled", file=sys.stderr)
        return 1
    release = NewRelease(args.package, args.old_version, args.new_version, "")
    written = analyzer.analyze(release, Path(args.cases_dir))
    print("\n".join(str(p) for p in written) or "(no cases generated)")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    """Seed candidates from release history (T12). Generation only; run `cycle` to verify."""
    analyzer = Analyzer()
    if not analyzer.enabled:
        print("ANTHROPIC_API_KEY not set; backfill needs the analyzer", file=sys.stderr)
        return 1
    releases: list[NewRelease] = []
    for package in args.packages:
        try:
            data = default_fetcher(package)
        except Exception as exc:  # one bad package must not kill the backfill
            print(f"[backfill] {package}: fetch error: {exc}", file=sys.stderr)
            continue
        pairs = historical_pairs(
            package, data, months=args.months, include_patch=args.include_patch
        )[: args.max_pairs]
        print(f"[backfill] {package}: {len(pairs)} release pair(s) in window")
        releases.extend(pairs)
    generated = _analyze(releases, Path(args.cases_dir), analyzer=analyzer)
    print(f"[backfill] {generated} candidate case(s) queued; run `libpulse cycle` to verify")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    written = Store(args.db).export_corpus(args.corpus_dir)
    print("\n".join(str(p) for p in written) or "(corpus empty)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .report import write_report

    path = write_report(Store(args.db), args.reports_dir)
    print(path)
    return 0


def cmd_prune_venvs(args: argparse.Namespace) -> int:
    """Remove verifier venvs untouched for N days (disk hygiene for the cron loop)."""
    import shutil

    cutoff = time.time() - args.keep_days * 86400
    removed = 0
    root = Path(args.venvs_dir)
    if root.exists():
        for venv in root.iterdir():
            if venv.is_dir() and venv.stat().st_mtime < cutoff:
                shutil.rmtree(venv, ignore_errors=True)
                removed += 1
    print(f"pruned {removed} venv(s) older than {args.keep_days}d")
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
        "cycle",
        help="unattended loop: watch releases, generate cases, ingest, verify, export, report",
    )
    p.set_defaults(func=cmd_cycle)

    p = sub.add_parser("analyze", help="generate candidate cases for one release (debugging aid)")
    p.add_argument("package")
    p.add_argument("old_version")
    p.add_argument("new_version")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser(
        "watch", help="poll PyPI for new final releases of tracked packages (one JSON line each)"
    )
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("backfill", help="seed candidates from the last N months of release history")
    p.add_argument("packages", nargs="+")
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--max-pairs", type=int, default=10, help="newest-first cap per package")
    p.add_argument(
        "--include-patch", action="store_true", help="also analyze patch-only version bumps"
    )
    p.set_defaults(func=cmd_backfill)

    p = sub.add_parser("export", help="re-export the verified corpus")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("report", help="write the weekly markdown report")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("prune-venvs", help="remove verifier venvs untouched for N days")
    p.add_argument("--keep-days", type=int, default=30)
    p.add_argument("--venvs-dir", default="venvs")
    p.set_defaults(func=cmd_prune_venvs)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
