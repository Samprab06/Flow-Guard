#!/usr/bin/env python3
"""Recompute aggregates and paired FlowGuard-minus-EI-only differences.

Reads ONLY committed replay outputs (no EDA, no optimizer runs):
  experiments/crossbar_v2/replay_36pool_combined13/per_seed_method_table.csv
  experiments/crossbar_v2/replay_36pool_combined13/curves_best_qor_vs_evals.csv
  experiments/crossbar_v2/replay_36pool_combined13/replay_36pool_combined13_results.json

Writes (into the bundle dir passed as argv[1]):
  03_recomputed_aggregates.json / .csv
  03_paired_flowguard_minus_eionly.csv / .json

Runtime columns are labeled as estimated sequential evaluation costs from
recorded physical runs (sums of committed ledger `runtime_s`); optimizer
overhead is reported separately and never mixed into EDA sums.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
COMBINED = ROOT / "experiments/crossbar_v2/replay_36pool_combined13"
TABLE_CSV = COMBINED / "per_seed_method_table.csv"
ORIGINAL_SEEDS = (11, 29, 47)


def mean(xs):
    return sum(xs) / len(xs)


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main(bundle_dir: str) -> int:
    out = Path(bundle_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(TABLE_CSV.open()))
    assert len(rows) == 39, f"expected 39 method x seed rows, got {len(rows)}"
    seeds = sorted({int(r["seed"]) for r in rows})
    assert seeds == [11, 29, 47, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149], seeds

    methods = ("vanilla_bo_penalty", "flowguard_calibrated", "ei_only_ablation")
    by_method = {m: [r for r in rows if r["method"] == m] for m in methods}
    assert all(len(v) == 13 for v in by_method.values())

    num = lambda r, k: float(r[k])  # noqa: E731
    agg = {}
    for m, rs in by_method.items():
        agg[m] = {
            "n_seeds": len(rs),
            "mean_best_qor": mean([num(r, "best_feasible_qor") for r in rs]),
            "median_best_qor": median([num(r, "best_feasible_qor") for r in rs]),
            "mean_feasible_count": mean([num(r, "feasible_count") for r in rs]),
            "median_feasible_count": median([num(r, "feasible_count") for r in rs]),
            "mean_first_feasible_call": mean([num(r, "first_feasible_call") for r in rs]),
            "mean_failed_eda_runtime_s": mean([num(r, "failed_eda_runtime_s") for r in rs]),
            "median_failed_eda_runtime_s": median([num(r, "failed_eda_runtime_s") for r in rs]),
            "mean_total_eda_runtime_s": mean([num(r, "total_eda_runtime_s") for r in rs]),
            "mean_optimizer_overhead_s": mean([num(r, "optimizer_overhead_s") for r in rs]),
            "mean_best_qor_call": mean([num(r, "best_qor_call") for r in rs]),
        }

    # Paired FlowGuard-minus-EI-only differences per seed.
    paired = []
    for s in seeds:
        fg = next(r for r in rows if int(r["seed"]) == s and r["method"] == "flowguard_calibrated")
        ei = next(r for r in rows if int(r["seed"]) == s and r["method"] == "ei_only_ablation")
        paired.append({
            "seed": s,
            "cohort": "original" if s in ORIGINAL_SEEDS else "extension",
            "d_best_qor": num(fg, "best_feasible_qor") - num(ei, "best_feasible_qor"),
            "d_best_qor_call": int(fg["best_qor_call"]) - int(ei["best_qor_call"]),
            "d_feasible_count": int(fg["feasible_count"]) - int(ei["feasible_count"]),
            "d_failed_eda_runtime_s": num(fg, "failed_eda_runtime_s") - num(ei, "failed_eda_runtime_s"),
            "d_total_eda_runtime_s": num(fg, "total_eda_runtime_s") - num(ei, "total_eda_runtime_s"),
            "d_optimizer_overhead_s": num(fg, "optimizer_overhead_s") - num(ei, "optimizer_overhead_s"),
        })

    payload = {
        "source": "experiments/crossbar_v2/replay_36pool_combined13/per_seed_method_table.csv",
        "n_rows": 39,
        "original_seeds": list(ORIGINAL_SEEDS),
        "runtime_label": "estimated sequential evaluation costs from recorded physical runs "
                         "(sums of committed ledger runtime_s); optimizer overhead reported separately",
        "aggregates_per_method": agg,
        "paired_flowguard_minus_eionly": paired,
    }
    (out / "03_recomputed_aggregates.json").write_text(json.dumps(payload, indent=2) + "\n")

    with (out / "03_recomputed_aggregates.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["method", "n_seeds", "mean_best_qor", "median_best_qor",
                    "mean_feasible_count", "median_feasible_count",
                    "mean_first_feasible_call", "mean_failed_eda_runtime_s",
                    "median_failed_eda_runtime_s", "mean_total_eda_runtime_s",
                    "mean_optimizer_overhead_s", "mean_best_qor_call"])
        for m in methods:
            a = agg[m]
            w.writerow([m, a["n_seeds"], f"{a['mean_best_qor']:.9f}", f"{a['median_best_qor']:.9f}",
                        f"{a['mean_feasible_count']:.4f}", a["median_feasible_count"],
                        f"{a['mean_first_feasible_call']:.4f}", f"{a['mean_failed_eda_runtime_s']:.3f}",
                        f"{a['median_failed_eda_runtime_s']:.3f}", f"{a['mean_total_eda_runtime_s']:.3f}",
                        f"{a['mean_optimizer_overhead_s']:.4f}", f"{a['mean_best_qor_call']:.4f}"])

    with (out / "03_paired_flowguard_minus_eionly.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seed", "cohort", "d_best_qor", "d_best_qor_call", "d_feasible_count",
                    "d_failed_eda_runtime_s", "d_total_eda_runtime_s", "d_optimizer_overhead_s"])
        for p in paired:
            w.writerow([p["seed"], p["cohort"], f"{p['d_best_qor']:.12f}", p["d_best_qor_call"],
                        p["d_feasible_count"], f"{p['d_failed_eda_runtime_s']:.3f}",
                        f"{p['d_total_eda_runtime_s']:.3f}", f"{p['d_optimizer_overhead_s']:.4f}"])
    (out / "03_paired_flowguard_minus_eionly.json").write_text(
        json.dumps(paired, indent=2) + "\n")

    # Cross-check against the committed combined REPORT headline means.
    checks = {
        "mean_best_qor_all_tie": len({round(agg[m]["mean_best_qor"], 9) for m in methods}) == 1,
        "mean_failed_vanilla": round(agg["vanilla_bo_penalty"]["mean_failed_eda_runtime_s"], 1),
        "mean_failed_flowguard": round(agg["flowguard_calibrated"]["mean_failed_eda_runtime_s"], 1),
        "mean_failed_eionly": round(agg["ei_only_ablation"]["mean_failed_eda_runtime_s"], 1),
        "paired_d_best_qor_all_zero": all(p["d_best_qor"] == 0.0 for p in paired),
        "paired_d_best_call_all_zero": all(p["d_best_qor_call"] == 0 for p in paired),
    }
    assert checks["mean_best_qor_all_tie"], "primary endpoint must be a 13-seed tie"
    for k in ("mean_failed_vanilla", "mean_failed_flowguard", "mean_failed_eionly"):
        assert abs(checks[k] - {"mean_failed_vanilla": 13046.8,
                                "mean_failed_flowguard": 14378.0,
                                "mean_failed_eionly": 14994.8}[k]) < 0.1, (k, checks[k])
    assert checks["paired_d_best_qor_all_zero"] and checks["paired_d_best_call_all_zero"]
    print("recompute OK:", json.dumps(checks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
