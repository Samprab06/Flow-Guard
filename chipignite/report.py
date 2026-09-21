"""Migration report generation with metadata fields retained verbatim."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .scoring import score_candidate


def migration_report(candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for candidate in candidates:
        row = dict(candidate)
        row["scoring"] = score_candidate(candidate)
        rows.append(row)
    return {"schema_version": 1, "candidate_count": len(rows), "candidates": rows}


def write_report(candidates: Iterable[dict[str, Any]], output: str | Path) -> dict[str, Any]:
    report = migration_report(candidates)
    Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
