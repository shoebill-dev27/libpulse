"""HuggingFace dataset export (T15): corpus -> dist/hf/ ready for `huggingface-cli upload`.

Builds the files only (dry run); the actual upload/publication is an owner
action. One JSONL row per verified case, plus a dataset card whose disclaimer
is required by SECURITY_REVIEW.md (published surfaces).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .corpus import list_packages, load_entries

CARD_TEMPLATE = """\
---
license: cc-by-4.0
language: en
tags:
  - python
  - breaking-changes
  - migration
  - code
pretty_name: LibPulse — execution-verified Python breaking changes
---

# LibPulse: execution-verified Python breaking changes & migration recipes

One row per breaking change between two versions of a popular PyPI package.
Every row passed a three-step execution proof in version-pinned environments:

1. `before` runs successfully on `old_version`;
2. `before` fails on `new_version` (the change is really breaking);
3. `after` (the migration recipe) runs successfully on `new_version`.

Generated {date}. Packages covered: {packages}. Rows: {rows}.

## Fields

| field | meaning |
|---|---|
| `package` | PyPI package name |
| `old_version` / `new_version` | version pair the change was proven against |
| `title` | one-line description of the removed/changed API |
| `before` | code that passes on old and fails on new |
| `after` | migrated code that passes on new |
| `after_works_on_old` | whether the recipe is also backward-compatible |
| `case_id` | stable content hash |

## Disclaimer

Snippets are LLM-generated and machine-verified **for pass/fail behavior
only**; they are not human-audited line by line. Execute third-party code at
your own discretion. Freshness: the corpus is maintained by an automated
pipeline watching new releases; a given pair reflects the state at
verification time.
"""


def build_dataset(out_dir: str | Path = "dist/hf", corpus: str | Path | None = None) -> Path:
    out = Path(out_dir)
    (out / "data").mkdir(parents=True, exist_ok=True)
    rows = 0
    packages = list_packages(corpus)
    with (out / "data" / "train.jsonl").open("w", encoding="utf-8") as fh:
        for row in sorted(packages, key=lambda r: r["package"]):
            for e in load_entries(row["package"], corpus):
                fh.write(json.dumps(e, sort_keys=True) + "\n")
                rows += 1
    card = CARD_TEMPLATE.format(
        date=time.strftime("%Y-%m-%d"),
        packages=", ".join(r["package"] for r in packages),
        rows=rows,
    )
    (out / "README.md").write_text(card, encoding="utf-8")
    return out
