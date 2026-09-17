"""Offline summaries and model sanity checks for v3 aggregate JSONL.

This module deliberately describes observed data only.  It does not run EDA,
select candidates, or claim optimizer performance.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "results" / "v3_aggregates" / "aggregated.jsonl"
MANIFEST_PATH = Path(__file__).with_name("manifests") / "v3_diagnostic_boundary.json"
FEATURES = ("FP_CORE_UTIL", "PL_TARGET_DENSITY_PCT", "GPL_CELL_PADDING", "GRT_ADJUSTMENT")
METRICS = ("area", "WNS", "TNS", "DRC", "wirelength")


def load_records(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read non-empty JSONL records, rejecting malformed lines."""
    source = Path(path) if path else DEFAULT_PATH
    records: list[dict[str, Any]] = []
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_number}: invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{source}:{line_number}: record must be an object")
            records.append(value)
    return records


def _number(record: dict[str, Any], name: str) -> float | None:
    aliases = (name, {"area": "cell_area", "WNS": "wns", "TNS": "tns", "DRC": "drc_violations", "wirelength": "routing_wirelength"}.get(name, name))
    for key in aliases:
        value = record.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def _feasible(record: dict[str, Any]) -> bool:
    value = record.get("feasible")
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


def _group_key(record: dict[str, Any]) -> str:
    knobs = record.get("knobs", {})
    if isinstance(knobs, str):
        try:
            knobs = json.loads(knobs)
        except json.JSONDecodeError:
            pass
    return json.dumps(knobs, sort_keys=True, separators=(",", ":"))


def summarize(records: Iterable[dict[str, Any]], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return metric ranges, repeatability requirements, and class balance."""
    rows = list(records)
    manifest = manifest or json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ranges: dict[str, dict[str, float | int] | None] = {}
    for metric in METRICS:
        values = [value for row in rows if (value := _number(row, metric)) is not None]
        ranges[metric] = {"min": min(values), "max": max(values), "count": len(values)} if values else None
    groups: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        groups[_group_key(row)] += 1
    required = int(manifest["repeatability"]["required_repeats_per_configuration"])
    undersized = sorted(count for count in groups.values() if count < required)
    feasible = sum(_feasible(row) for row in rows)
    total = len(rows)
    fractions = {"false": (total - feasible) / total if total else 0.0, "true": feasible / total if total else 0.0}
    missing_metrics: Counter[str] = Counter()
    failure_stages: Counter[str] = Counter()
    for row in rows:
        missing = row.get("missing_metrics", [])
        if isinstance(missing, str):
            try:
                missing = json.loads(missing)
            except json.JSONDecodeError:
                missing = [missing]
        for name in missing or []:
            missing_metrics[str(name)] += 1
        stage = row.get("failure_stage")
        if stage:
            failure_stages[str(stage)] += 1
    warnings: list[str] = []
    if total and len({ _feasible(row) for row in rows }) == 1:
        warnings.append("all trials are one feasibility class; model sanity checks are limited")
    minimum = float(manifest["feasibility_balance"]["minimum_class_fraction"])
    if total and min(fractions.values()) < minimum:
        warnings.append(f"feasibility balance below minimum class fraction {minimum:g}")
    return {
        "manifest_version": manifest.get("manifest_version", manifest.get("schema", "unknown")),
        "records": total,
        "metric_ranges": ranges,
        "repeatability": {"groups": len(groups), "sizes": dict(sorted(Counter(groups.values()).items())), "required_repeats_per_configuration": required, "undersized_groups": len(undersized)},
        "feasibility_balance": {"counts": {"false": total - feasible, "true": feasible}, "fractions": fractions},
        "evidence_gaps": {
            "missing_metrics": dict(sorted(missing_metrics.items())),
            "failure_stages": dict(sorted(failure_stages.items())),
        },
        "warnings": warnings,
    }


def leave_one_out(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Assess feasible-only QoR holdouts against a training mean.

    This is a sanity baseline, not an optimizer evaluation.  A held-out row is
    scored only when at least one other feasible row has the metric.
    """
    feasible = [row for row in records if _feasible(row)]
    result: dict[str, Any] = {"claim": "sanity baseline only; no optimizer result", "feasible_records": len(feasible), "metrics": {}}
    for metric in ("area", "WNS"):
        errors: list[float] = []
        for index, row in enumerate(feasible):
            actual = _number(row, metric)
            training = [_number(other, metric) for j, other in enumerate(feasible) if j != index]
            training = [value for value in training if value is not None]
            if actual is not None and training:
                errors.append(abs(actual - sum(training) / len(training)))
        result["metrics"][metric] = {"evaluated": len(errors), "mae": sum(errors) / len(errors) if errors else None}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", help=f"v3 aggregate JSONL (default: {DEFAULT_PATH})")
    parser.add_argument("--model-sanity", "--leave-one-out", action="store_true", help="include feasible-only leave-one-out QoR sanity baseline")
    args = parser.parse_args(argv)
    records = load_records(args.path)
    report = summarize(records)
    if args.model_sanity:
        report["model_sanity"] = leave_one_out(records)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
