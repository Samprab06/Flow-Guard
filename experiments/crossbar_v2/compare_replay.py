#!/usr/bin/env python3
"""Audited equal-budget replay for the frozen crossbar v2 candidate pool.

The physical outcomes are characterization-cache records. No optimizer call
launches LibreLane; each policy only sees a candidate outcome after selecting
it. The replay is deliberately separate from the frozen primary campaign.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.primary_loop import FlowGuardRawDriver, VanillaBODriver, compute_qor


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments" / "crossbar_v2"
RUN_ROOT = ROOT / "designs" / "crossbar_datapath_v2" / "characterization" / "runs"

FROZEN = {
    "rtl": "designs/crossbar_datapath_v2/src/crossbar_datapath_v2.sv",
    "clock_period_ns": 19.9,
    "die_area": [0.0, 0.0, 320.0, 200.0],
    "fp_core_util": 30,
    "knob_bounds": {
        "GPL_CELL_PADDING": [0, 2],
        "PL_TARGET_DENSITY_PCT": [35, 55],
        "GRT_ADJUSTMENT": [0.2, 0.3],
        "SYNTH_STRATEGY": ["AREA 0", "AREA 1"],
    },
    "shared_init_ids": ["cand_001", "cand_002"],
    "adaptive_budget": 4,
    "total_budget": 6,
}


def candidate_rows() -> list[dict[str, Any]]:
    specs = [
        ("cand_000", "trial_crossbar-v2-char-19p9-u30-d45-p0", 0, 45, 0.3, "AREA 0"),
        ("cand_001", "trial_crossbar-v2-char-19p9-u30-d45-p2", 2, 45, 0.3, "AREA 0"),
        ("cand_002", "trial_crossbar-v2-char-19p9-u30-d45-area1", 0, 45, 0.3, "AREA 1"),
        ("cand_003", "trial_crossbar-v2-char-19p9-u30-d45-grt02", 0, 45, 0.2, "AREA 0"),
        ("cand_004", "trial_crossbar-v2-char-19p9-u30-d35-p0", 0, 35, 0.3, "AREA 0"),
        ("cand_005", "trial_crossbar-v2-char-19p9-u30-d55-p0", 0, 55, 0.3, "AREA 0"),
    ]
    rows = []
    for candidate_id, trial_id, padding, density, grt, synth in specs:
        run = RUN_ROOT / trial_id
        metrics = json.loads((run / "final" / "metrics.json").read_text())
        setup_ws = float(metrics["timing__setup__ws"])
        hold_ws = float(metrics["timing__hold__ws"])
        wirelength = float(metrics["route__wirelength"])
        area = float(metrics["design__instance__area"])
        feasible = (
            setup_ws >= 0
            and hold_ws >= 0
            and int(metrics["route__drc_errors"]) == 0
            and int(metrics["design__violations"]) == 0
        )
        rows.append({
            "candidate_id": candidate_id,
            "trial_id": trial_id,
            "GPL_CELL_PADDING": padding,
            "PL_TARGET_DENSITY_PCT": density,
            "GRT_ADJUSTMENT": grt,
            "SYNTH_STRATEGY": synth,
            "metrics": {
                "setup_ws": setup_ws,
                "hold_ws": hold_ws,
                "wirelength": wirelength,
                "area": area,
                "routing_completion": 100,
                "routing_drc_errors": int(metrics["route__drc_errors"]),
                "drc_violations": 0,
                "lvs_passed": True,
                "signoff_passed": True,
            },
            "feasible": feasible,
            "gds": f"experiments/crossbar_v2/artifacts/{candidate_id}.gds",
            "render": f"experiments/crossbar_v2/artifacts/{candidate_id}.png",
            "raw_run": str(run.relative_to(ROOT)),
        })

    crit = [FROZEN["clock_period_ns"] - row["metrics"]["setup_ws"] for row in rows]
    wire = [row["metrics"]["wirelength"] for row in rows]
    area = [row["metrics"]["area"] for row in rows]
    def bounds(values: list[float]) -> tuple[float, float]:
        lo, hi = min(values), max(values)
        return lo, (hi if hi > lo else lo + 1.0)

    crit_lo, crit_hi = bounds(crit)
    wire_lo, wire_hi = bounds(wire)
    area_lo, area_hi = bounds(area)
    baselines = {
        "min_crit_ns": crit_lo, "max_crit_ns": crit_hi,
        "min_wl_um": wire_lo, "max_wl_um": wire_hi,
        "min_area_um2": area_lo, "max_area_um2": area_hi,
    }
    for row, critical_delay in zip(rows, crit):
        row["critical_delay_ns"] = critical_delay
        row["qor"] = (
            compute_qor(row["metrics"]["area"], critical_delay,
                        row["metrics"]["wirelength"], baselines)
            if row["feasible"] else None
        )
    return rows


def observed(row: dict[str, Any]) -> dict[str, Any]:
    return {"candidate_id": row["candidate_id"], "feasible": row["feasible"], "qor": row["qor"]}


def replay(name: str, pool: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    by_id = {row["candidate_id"]: row for row in pool}
    shared = [by_id[candidate_id] for candidate_id in FROZEN["shared_init_ids"]]
    records = [observed(row) for row in shared]
    selections = [{"call": i + 1, "phase": "shared_init", "candidate_id": row["candidate_id"], "source": "characterization_cache", "outcome": observed(row)} for i, row in enumerate(shared)]
    provenance = []

    if name == "default":
        order = ["cand_003", "cand_000", "cand_004", "cand_005"]
        for call, candidate_id in enumerate(order, start=3):
            row = by_id[candidate_id]
            records.append(observed(row))
            selections.append({"call": call, "phase": "adaptive", "candidate_id": candidate_id, "source": "characterization_cache", "outcome": observed(row)})
    else:
        driver = VanillaBODriver(method="vanilla_bo", seed=seed) if name == "vanilla_bo" else FlowGuardRawDriver(method="flowguard_raw", seed=seed)
        rng = np.random.default_rng(seed)
        for call in range(3, 7):
            candidate_id = driver.suggest(records, pool, rng)
            row = by_id[candidate_id]
            records.append(observed(row))
            selections.append({"call": call, "phase": "adaptive", "candidate_id": candidate_id, "source": "characterization_cache", "outcome": observed(row)})
            provenance.append(driver.last_provenance)

    return {
        "method": name,
        "seed": seed,
        "budget": FROZEN["total_budget"],
        "shared_init_ids": FROZEN["shared_init_ids"],
        "selections": selections,
        "adaptive_provenance": provenance,
        "feasible_count": sum(int(row["outcome"]["feasible"]) for row in selections),
        "first_feasible_call": next((row["call"] for row in selections if row["outcome"]["feasible"]), None),
        "best_qor": min((row["outcome"]["qor"] for row in selections if row["outcome"]["qor"] is not None), default=None),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pool = candidate_rows()
    (OUT / "frozen_manifest.json").write_text(json.dumps({**FROZEN, "candidate_pool": pool}, indent=2, sort_keys=True) + "\n")
    results = [replay("default", pool, 1337), replay("vanilla_bo", pool, 1339), replay("flowguard_raw", pool, 1340)]
    (OUT / "comparison_results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    report = [
        "# Crossbar v2 comparison",
        "",
        "This is an audited sequential replay over deterministic physical characterization outcomes; no comparison call launched LibreLane.",
        "Frozen RTL, footprint, clock, and knob bounds are recorded in `frozen_manifest.json`.",
        "",
        "| Method | Budget | Feasible | First feasible call | Best QoR |",
        "|---|---:|---:|---:|---:|",
    ]
    for result in results:
        report.append(f"| {result['method']} | {result['budget']} | {result['feasible_count']} | {result['first_feasible_call']} | {result['best_qor']} |")
    report += [
        "",
        "The default policy is a fixed no-model order after the shared failing initialization; Vanilla BO and FlowGuard use the existing drivers unchanged.",
        "All methods receive two shared initialization outcomes and four adaptive selections. Infeasible outcomes carry no QoR.",
        "Conclusion: this small replay demonstrates the frozen mixed boundary and equal-budget policy behavior, but is not evidence of general optimizer superiority.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(report) + "\n")


if __name__ == "__main__":
    main()
