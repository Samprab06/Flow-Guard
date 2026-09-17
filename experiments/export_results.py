"""Export every ledgered trial into one CSV + summary JSON.

Read-only over results/*/trials.jsonl. Rerun at any time; the summary marks
methods that are still partial. Usage:
    python3 experiments/export_results.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMESPACES = [
    "exhaustive_clock_sweep_v1",
    "clock_hunt_16ns_v1",
    "clock_hunt_15p8ns_v1",
    "repeat_15p8_med_v1",
    "diag_15p8_v1",
    "primary-init-v1",
    "primary-random-v1",
    "primary-optuna_tpe-v1",
    "primary-vanilla_bo-v1",
    "primary-flowguard_raw-v1",
    "primary-flowguard_calibrated-v1",
]
COLUMNS = [
    "namespace", "method", "trial_id", "candidate_id", "clock_ns", "feasible",
    "qor", "setup_ws", "hold_ws", "area", "wirelength", "failure_stage",
    "runtime_s", "finished_at",
]


def method_of(namespace: str) -> str:
    if namespace == "primary-init-v1":
        return "shared-init"
    if namespace.startswith("primary-"):
        return namespace[len("primary-"):-len("-v1")]
    return "characterization"


def main() -> int:
    rows = []
    for ns in NAMESPACES:
        path = ROOT / "results" / ns / "trials.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            metrics = record.get("metrics") or {}
            rows.append({
                "namespace": ns,
                "method": method_of(ns),
                "trial_id": record.get("trial_id"),
                "candidate_id": record.get("candidate_id"),
                "clock_ns": record.get("clock_ns"),
                "feasible": record.get("feasible"),
                "qor": record.get("qor"),
                "setup_ws": metrics.get("setup_ws"),
                "hold_ws": metrics.get("hold_ws"),
                "area": metrics.get("area"),
                "wirelength": metrics.get("wirelength"),
                "failure_stage": metrics.get("failure_stage"),
                "runtime_s": metrics.get("runtime_s"),
                "finished_at": record.get("finished_at"),
            })
    out_dir = ROOT / "results"
    csv_path = out_dir / "flowguard_results_export.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    summary = {"total_trials": len(rows), "by_namespace": {}, "primary_methods": {}}
    for row in rows:
        bucket = summary["by_namespace"].setdefault(
            row["namespace"], {"trials": 0, "feasible": 0, "fails": 0})
        bucket["trials"] += 1
        bucket["feasible" if row["feasible"] else "fails"] += 1
    for row in rows:
        if row["method"] in {"shared-init", "characterization"}:
            continue
        bucket = summary["primary_methods"].setdefault(
            row["method"], {"calls": 0, "feasible": 0, "fails": 0, "best_qor": None,
                            "best_candidate": None})
        bucket["calls"] += 1
        if row["feasible"]:
            bucket["feasible"] += 1
            if row["qor"] is not None and (bucket["best_qor"] is None or row["qor"] < bucket["best_qor"]):
                bucket["best_qor"] = row["qor"]
                bucket["best_candidate"] = row["candidate_id"]
        else:
            bucket["fails"] += 1
    summary["partial"] = [
        name for name, b in summary["primary_methods"].items() if b["calls"] < 16]
    summary_path = out_dir / "flowguard_results_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {csv_path} ({len(rows)} rows)")
    print(f"wrote {summary_path}")
    for name, b in sorted(summary["primary_methods"].items()):
        print(f"  {name:22s} calls={b['calls']:2d} feas={b['feasible']:2d} fails={b['fails']:2d} "
              f"best={b['best_qor'] if b['best_qor'] is None else round(b['best_qor'], 4)} "
              f"({b['best_candidate']})")
    if summary["partial"]:
        print("partial:", ", ".join(summary["partial"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
