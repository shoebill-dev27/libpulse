"""Core data model: a migration case and its execution-verified verdict."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum


class Verdict(str, Enum):
    # All three executions behaved as claimed: before passes on old,
    # before fails on new (proves the change is breaking), after passes on new.
    VERIFIED = "verified"
    # The "before" snippet still passes on the new version: not a breaking change.
    NOT_BREAKING = "not_breaking"
    # The migrated "after" snippet fails on the new version: recipe is wrong.
    BROKEN_RECIPE = "broken_recipe"
    # Environment setup failed or the snippet is invalid on the old version;
    # nothing can be claimed either way.
    UNVERIFIABLE = "unverifiable"


@dataclass
class MigrationCase:
    """One claimed breaking change with a migration recipe, as executable evidence.

    before_snippet must pass on old_version and fail on new_version.
    after_snippet must pass on new_version.
    """

    package: str
    old_version: str
    new_version: str
    title: str
    before_snippet: str
    after_snippet: str
    extra_requires: list[str] = field(default_factory=list)
    source: str = ""  # provenance: release-notes/changelog URL
    case_id: str = ""

    def __post_init__(self) -> None:
        if not self.case_id:
            self.case_id = self.compute_id()

    def compute_id(self) -> str:
        key = "|".join([self.package, self.old_version, self.new_version, self.title])
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MigrationCase":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_json_file(cls, path: str) -> "MigrationCase":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


@dataclass
class StepResult:
    """Outcome of executing one snippet in one environment."""

    step: str  # e.g. "before_on_old"
    passed: bool
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerificationResult:
    case_id: str
    verdict: Verdict
    steps: list[StepResult] = field(default_factory=list)
    after_works_on_old: bool | None = None  # informational: recipe is backward-compatible
    error: str = ""  # populated for UNVERIFIABLE
    verified_at: float = field(default_factory=time.time)
    harness_version: str = "0.1.0"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d
