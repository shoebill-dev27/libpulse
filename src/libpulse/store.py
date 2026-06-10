"""Corpus storage: SQLite working store + deterministic JSON export for git.

The exported JSON under data/corpus/ is the published asset; the SQLite file is
a local working store and is not committed.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .models import MigrationCase, Verdict, VerificationResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    package TEXT NOT NULL,
    old_version TEXT NOT NULL,
    new_version TEXT NOT NULL,
    title TEXT NOT NULL,
    before_snippet TEXT NOT NULL,
    after_snippet TEXT NOT NULL,
    extra_requires TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS results (
    case_id TEXT PRIMARY KEY REFERENCES cases(case_id),
    verdict TEXT NOT NULL,
    after_works_on_old INTEGER,
    error TEXT NOT NULL DEFAULT '',
    steps_json TEXT NOT NULL DEFAULT '[]',
    verified_at REAL NOT NULL,
    harness_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_package ON cases(package);
"""


class Store:
    def __init__(self, db_path: str | Path = "data/libpulse.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_case(self, case: MigrationCase) -> None:
        self.conn.execute(
            """INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(case_id) DO UPDATE SET
                 title=excluded.title, before_snippet=excluded.before_snippet,
                 after_snippet=excluded.after_snippet, extra_requires=excluded.extra_requires,
                 source=excluded.source""",
            (
                case.case_id,
                case.package,
                case.old_version,
                case.new_version,
                case.title,
                case.before_snippet,
                case.after_snippet,
                json.dumps(case.extra_requires),
                case.source,
                time.time(),
            ),
        )
        self.conn.commit()

    def save_result(self, result: VerificationResult) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?)",
            (
                result.case_id,
                result.verdict.value,
                None if result.after_works_on_old is None else int(result.after_works_on_old),
                result.error,
                json.dumps([s.to_dict() for s in result.steps]),
                result.verified_at,
                result.harness_version,
            ),
        )
        self.conn.commit()

    def get_case(self, case_id: str) -> MigrationCase | None:
        row = self.conn.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["extra_requires"] = json.loads(d["extra_requires"])
        d.pop("created_at")
        return MigrationCase.from_dict(d)

    def pending_case_ids(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT c.case_id FROM cases c LEFT JOIN results r USING(case_id) WHERE r.case_id IS NULL"
        ).fetchall()
        return [r["case_id"] for r in rows]

    def verdict_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT verdict, COUNT(*) n FROM results GROUP BY verdict"
        ).fetchall()
        return {r["verdict"]: r["n"] for r in rows}

    def export_corpus(self, out_dir: str | Path = "data/corpus") -> list[Path]:
        """Write VERIFIED entries as deterministic per-package JSON files."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        rows = self.conn.execute(
            """SELECT c.*, r.after_works_on_old, r.verified_at FROM cases c
               JOIN results r USING(case_id) WHERE r.verdict=?
               ORDER BY c.package, c.new_version, c.case_id""",
            (Verdict.VERIFIED.value,),
        ).fetchall()
        by_package: dict[str, list[dict]] = {}
        for row in rows:
            d = dict(row)
            entry = {
                "case_id": d["case_id"],
                "package": d["package"],
                "old_version": d["old_version"],
                "new_version": d["new_version"],
                "title": d["title"],
                "before": d["before_snippet"],
                "after": d["after_snippet"],
                "extra_requires": json.loads(d["extra_requires"]),
                "source": d["source"],
                "after_works_on_old": (
                    bool(d["after_works_on_old"]) if d["after_works_on_old"] is not None else None
                ),
                "verified_at": int(d["verified_at"]),
                "verdict": "verified",
            }
            by_package.setdefault(d["package"], []).append(entry)
        written = []
        for package, entries in sorted(by_package.items()):
            path = out / f"{package}.json"
            path.write_text(
                json.dumps({"package": package, "entries": entries}, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            written.append(path)
        return written
