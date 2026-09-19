#!/usr/bin/env python3
"""Offline sequential replay over the committed 36-point physical oracle.

Reads outcomes ONLY from experiments/crossbar_v2/char36_results_ledger.json.
Launches no EDA/LibreLane processes, edits no RTL/primary files, runs no
optimizer outside this replay. Each trace sees an outcome only after
selecting that candidate (HiddenOracle); unselected outcomes stay hidden.

Design (predeclared):
  * Seeds: 11, 29, 47 (exact).
  * Shared init per seed: 8 candidate IDs drawn once per seed with
    numpy.random.default_rng(seed).choice(36, 8, replace=False) in drawn
    order; identical across the three methods within a seed.
  * Adaptive budget 16 per method, total 24 per method (8 + 16).
  * Methods:
      - vanilla_bo_penalty: src.primary_loop.VanillaBODriver (GP on all
        observed with INFEASIBLE_PENALTY=1.0, plain EI, p_feas=1.0).
      - flowguard_calibrated: src.primary_loop.FlowGuardCalibratedDriver
        (feasible-only QoR GP, EI x P(feasible) from RF with sigmoid
        calibration iff >=3 samples per class, else uncalibrated fallback).
      - ei_only_ablation: same feasible-only QoR GP preprocessing/fitting
        (scale_features / fit_qor_gp) and EI acquisition
        (expected_improvement) as FlowGuard, but p_feas fixed to 1.0 and
        no feasibility classifier of any kind.
  * Identical fallback until first feasible: whenever the observed set has
    zero feasible records, ALL methods select argmax P(feasible) from a
    freshly fitted src.models.FeasibilityModel on the observed data
    (ties -> first in pool order). This overrides Vanilla's native
    penalty-GP ranking in the pre-feasible regime so the comparison
    isolates post-feasible acquisition behavior.
  * Driver GP randomness: driver seed = replay seed (matched across
    methods); FeasibilityModel randomness is frozen internally
    (random_state=0). No other randomness; ties break to pool order
    via numpy argmax.
  * No-feasible handling: best feasible QoR reported as null with
    best_qor_inf=true (+inf semantics: worse than any feasible score).

Usage:
  .venv/ml/bin/python experiments/crossbar_v2/replay_36pool_offline.py
"""

from __future__ import annotations

import json
import sys
import time
from copy import deepcopy
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.models import FeasibilityModel  # noqa: E402
from src.primary_loop import (  # noqa: E402
    MODEL_VERSIONS,
    FlowGuardCalibratedDriver,
    VanillaBODriver,
    compute_data_hash,
    expected_improvement,
    fit_qor_gp,
    gp_predict,
    scale_features,
)

LEDGER = ROOT / "experiments" / "crossbar_v2" / "char36_results_ledger.json"
OUT_DIR = ROOT / "experiments" / "crossbar_v2" / "replay_36pool_offline"

SEEDS = (11, 29, 47)
SHARED_INIT_N = 8
ADAPTIVE_N = 16
TOTAL_N = SHARED_INIT_N + ADAPTIVE_N

METHODS = ("vanilla_bo_penalty", "flowguard_calibrated", "ei_only_ablation")

EDA_PROCESS_PATTERNS = (
    "openlane", "librelane", "openroad", "yosys", "klayout", "magic",
    "netgen", "ngspice", "xyce",
)


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.ndarray,)):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def self_check_no_physical_surface() -> list[str]:
    """Static guard: this script must never import launch/compute surfaces.

    Scans import statements only (substring scans snag benign identifiers
    such as `physical_runs_launched`). Returns the banned tokens screened
    (empty hits); raises if any banned import is present.
    """
    text = Path(__file__).read_text(encoding="utf-8")
    banned = ["subprocess", "docker", "openlane", "librelane",
              "klayout", "yosys", "openroad", "src.runner", "os"]
    import_hits = [line.strip() for line in text.splitlines()
                   if line.strip().startswith(("import ", "from "))
                   and any(tok in line for tok in banned)]
    assert not import_hits, f"banned imports present: {import_hits}"
    return []


def snapshot_processes() -> dict[str, object]:
    """Read-only process snapshot via /proc; counts EDA-named entries."""
    try:
        names: list[str] = []
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            comm = pid_dir / "comm"
            try:
                names.append(comm.read_text(encoding="utf-8").strip().lower())
            except OSError:
                continue
    except Exception as exc:  # /proc unavailable: record, do not fail closed
        return {"ps_available": False, "error": str(exc),
                "eda_matches": [], "eda_count": None}
    matches = sorted({name for name in names
                      if any(pat in name for pat in EDA_PROCESS_PATTERNS)})
    return {"ps_available": True, "eda_matches": matches,
            "eda_count": len(matches), "total_processes": len(names)}


def load_oracle() -> tuple[list[dict], dict[str, dict]]:
    """Load committed ledger outcomes (sole data source). No EDA contact."""
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    entries = sorted(ledger["entries"], key=lambda e: e["pool_index"])
    assert len(entries) == 36, f"oracle pool size {len(entries)} != 36"
    assert [e["pool_candidate_id"] for e in entries] == \
        [f"cb36_{i:03d}" for i in range(36)], "oracle pool order drift"
    pool, outcomes = [], {}
    for entry in entries:
        knobs = entry["knobs"]
        pool.append({
            "candidate_id": entry["pool_candidate_id"],
            "pool_index": entry["pool_index"],
            "GPL_CELL_PADDING": knobs["GPL_CELL_PADDING"],
            "PL_TARGET_DENSITY_PCT": knobs["PL_TARGET_DENSITY_PCT"],
            "GRT_ADJUSTMENT": knobs["GRT_ADJUSTMENT"],
            "SYNTH_STRATEGY": knobs["SYNTH_STRATEGY"],
        })
        outcomes[entry["pool_candidate_id"]] = {
            "feasible": bool(entry["feasible"]),
            "qor": (float(entry["frozen_qor"])
                    if entry["feasible"] else None),
            "runtime_s": float(entry["runtime_s"]),
            "area": entry["area"],
            "wirelength": entry["wirelength"],
            "critical_delay_ns": entry["critical_delay_ns"],
            "setup_ws": entry["setup_ws"],
            "hold_ws": entry["hold_ws"],
            "drc_violations": entry["drc_violations"],
            "lvs_passed": entry["lvs_passed"],
            "signoff_passed": entry["signoff_passed"],
            "trial_id": entry["trial_id"],
            "pool_index": entry["pool_index"],
        }
    feas = sum(1 for o in outcomes.values() if o["feasible"])
    assert feas == 6, f"oracle feasible count {feas} != 6"
    return pool, outcomes


def init_ids_for_seed(seed: int) -> list[str]:
    """8 shared init IDs per seed, drawn order, identical across methods."""
    rng = np.random.default_rng(seed)
    picked = rng.choice(36, size=SHARED_INIT_N, replace=False).tolist()
    return [f"cb36_{i:03d}" for i in picked]


class HiddenOracle:
    """Reveals one committed outcome per selected ID; nothing else."""

    def __init__(self, outcomes: dict[str, dict]) -> None:
        self._outcomes = outcomes
        self.revealed: list[str] = []
        self._revealed_set: set[str] = set()

    def reveal(self, candidate_id: str) -> dict:
        if candidate_id in self._revealed_set:
            raise ValueError(f"duplicate selection {candidate_id}")
        if candidate_id not in self._outcomes:
            raise ValueError(f"unknown candidate {candidate_id}")
        self._revealed_set.add(candidate_id)
        self.revealed.append(candidate_id)
        return deepcopy(self._outcomes[candidate_id])


def shared_prefeasible_fallback(observed: list[dict], pool: list[dict],
                                unobserved: list[dict]) -> tuple[str, dict]:
    """Identical fallback for all methods while zero feasible observed.

    Fits src.models.FeasibilityModel on all observed (scaled features) and
    returns argmax P(feasible); single-class data falls back to the model
    constant (all-zero -> first in pool order). Ties -> pool order.
    """
    _, x_unobs = scale_features(pool, unobserved)
    pool_ids = [str(row["candidate_id"]) for row in pool]
    x_pool, _ = scale_features(pool, pool)
    by_pos = {cid: pos for pos, cid in enumerate(pool_ids)}
    x_all = np.array([x_pool[by_pos[r["candidate_id"]]] for r in observed])
    y_all = np.array([bool(r["feasible"]) for r in observed])
    model = FeasibilityModel().fit(x_all.tolist(), y_all.tolist())
    p_feas = np.asarray(model.predict_proba(x_unobs.tolist()), dtype=float)
    position = int(np.argmax(p_feas))
    return str(unobserved[position]["candidate_id"]), {
        "fallback": "shared-prefeasible-rf-pfeas",
        "calibration_active": bool(model.calibrated),
        "p_feas": float(p_feas[position]),
    }


def ei_only_suggest(observed: list[dict], pool: list[dict],
                    unobserved: list[dict], seed: int,
                    call_index: int) -> tuple[str, dict]:
    """EI-only ablation: feasible-only QoR GP + plain EI, p_feas == 1.0."""
    feasible = [r for r in observed if r["feasible"]]
    if not feasible:
        raise RuntimeError("ei_only requires >=1 feasible; use shared fallback")
    _, x_unobs = scale_features(pool, unobserved)
    pool_ids = [str(row["candidate_id"]) for row in pool]
    x_pool, _ = scale_features(pool, pool)
    by_pos = {cid: pos for pos, cid in enumerate(pool_ids)}
    x_feas = np.array([x_pool[by_pos[r["candidate_id"]]] for r in feasible])
    y_feas = np.array([float(r["qor"]) for r in feasible])
    best = float(np.min(y_feas))
    model = fit_qor_gp(x_feas, y_feas, seed)
    mean, var = gp_predict(model, x_unobs)
    ei = expected_improvement(mean, var, best)
    position = int(np.argmax(ei))
    prov = {
        "method": "ei_only_ablation",
        "seed": seed,
        "call_index": call_index,
        "training_candidate_ids": [r["candidate_id"] for r in observed],
        "training_size": len(observed),
        "data_hash": compute_data_hash(observed),
        "model_versions": dict(MODEL_VERSIONS),
        "calibration_active": False,
        "calibration_detail": "ei-only: no feasibility classifier, p_feas=1.0",
        "pred_mean": float(mean[position]),
        "pred_var": float(var[position]),
        "p_feas": 1.0,
        "ei": float(ei[position]),
        "acquisition_score": float(ei[position]),
        "rank": int(1 + np.sum(ei > ei[position])),
        "n_candidates_scored": len(unobserved),
        "selected_id": str(unobserved[position]["candidate_id"]),
    }
    return prov["selected_id"], prov


def run_trace(seed: int, method: str, pool: list[dict],
              outcomes: dict[str, dict]) -> dict:
    oracle = HiddenOracle(outcomes)
    by_id = {row["candidate_id"]: row for row in pool}
    init_ids = init_ids_for_seed(seed)
    assert len(set(init_ids)) == SHARED_INIT_N
    assert all(cid in by_id for cid in init_ids)

    if method == "vanilla_bo_penalty":
        driver = VanillaBODriver(method="vanilla_bo", seed=seed)
    elif method == "flowguard_calibrated":
        driver = FlowGuardCalibratedDriver(method="flowguard_calibrated",
                                           seed=seed)
    elif method == "ei_only_ablation":
        driver = None
    else:
        raise ValueError(f"unknown method {method}")
    rng = np.random.default_rng(seed)

    trace_wall_start = time.perf_counter()
    observed: list[dict] = []
    calls: list[dict] = []
    best_qor: float | None = None
    best_qor_call: int | None = None
    first_feasible_call: int | None = None
    feas_count = 0
    cum_failed_rt = 0.0
    cum_total_rt = 0.0
    overhead_total = 0.0
    fallback_uses = 0

    def record(call: int, phase: str, cid: str, outcome: dict,
               overhead: float, provenance: dict | None,
               fallback: dict | None) -> None:
        nonlocal best_qor, best_qor_call, first_feasible_call
        nonlocal feas_count, cum_failed_rt, cum_total_rt, overhead_total
        observed.append({"candidate_id": cid,
                         "feasible": outcome["feasible"],
                         "qor": outcome["qor"]})
        feas = bool(outcome["feasible"])
        if feas:
            feas_count += 1
            if first_feasible_call is None:
                first_feasible_call = call
            if best_qor is None or float(outcome["qor"]) < best_qor:
                best_qor = float(outcome["qor"])
                best_qor_call = call
        else:
            cum_failed_rt += float(outcome["runtime_s"])
        cum_total_rt += float(outcome["runtime_s"])
        overhead_total += float(overhead)
        calls.append({
            "call": call,
            "phase": phase,
            "candidate_id": cid,
            "feasible": feas,
            "qor": outcome["qor"],
            "best_feasible_qor": best_qor,
            "best_feasible_qor_call": best_qor_call,
            "first_feasible_call": first_feasible_call,
            "feasible_count": feas_count,
            "infeasible_count": call - feas_count,
            "cum_failed_eda_runtime_s": cum_failed_rt,
            "cum_total_eda_runtime_s": cum_total_rt,
            "optimizer_overhead_s": float(overhead),
            "cum_optimizer_overhead_s": overhead_total,
            "fallback_used": fallback is not None,
            "fallback_detail": fallback,
            "provenance": _jsonable(provenance) if provenance else None,
        })

    for i, cid in enumerate(init_ids):
        outcome = oracle.reveal(cid)
        record(i + 1, "shared_init", cid, outcome, 0.0, None, None)

    for step in range(ADAPTIVE_N):
        call = SHARED_INIT_N + step + 1
        unobserved = [row for row in pool
                      if row["candidate_id"] not in oracle._revealed_set]
        n_feas = sum(1 for r in observed if r["feasible"])
        fallback = None
        provenance = None
        t0 = time.perf_counter()
        if n_feas == 0:
            cid, fallback = shared_prefeasible_fallback(
                observed, pool, unobserved)
            fallback_uses += 1
        elif method == "ei_only_ablation":
            cid, provenance = ei_only_suggest(
                observed, pool, unobserved, seed, call)
        else:
            assert driver is not None
            driver.call_index = call
            cid = driver.suggest(list(observed), pool, rng)
            provenance = deepcopy(driver.last_provenance)
        overhead = time.perf_counter() - t0
        outcome = oracle.reveal(cid)
        record(call, "adaptive", cid, outcome, overhead,
               provenance, fallback)

    trace_wall = time.perf_counter() - trace_wall_start
    assert len(oracle.revealed) == TOTAL_N
    assert len({c["candidate_id"] for c in calls}) == TOTAL_N

    if best_qor is not None:
        best_call_rec = next(c for c in calls
                             if c["call"] == best_qor_call)
        best_outcome = outcomes[best_call_rec["candidate_id"]]
        final_metrics = {
            "candidate_id": best_call_rec["candidate_id"],
            "qor": best_qor,
            "area": best_outcome["area"],
            "wirelength": best_outcome["wirelength"],
            "critical_delay_ns": best_outcome["critical_delay_ns"],
            "setup_ws": best_outcome["setup_ws"],
            "hold_ws": best_outcome["hold_ws"],
            "drc_violations": best_outcome["drc_violations"],
            "lvs_passed": best_outcome["lvs_passed"],
            "signoff_passed": best_outcome["signoff_passed"],
            "runtime_s": best_outcome["runtime_s"],
            "trial_id": best_outcome["trial_id"],
        }
    else:
        final_metrics = None

    return {
        "method": method,
        "seed": seed,
        "shared_init_ids": init_ids,
        "budget": {"shared_init": SHARED_INIT_N,
                   "adaptive": ADAPTIVE_N, "total": TOTAL_N},
        "selected_ids": [c["candidate_id"] for c in calls],
        "calls": calls,
        "summary": {
            "method": method,
            "seed": seed,
            "best_feasible_qor": best_qor,
            "best_qor_inf": best_qor is None,
            "first_feasible_call": first_feasible_call,
            "best_qor_call": best_qor_call,
            "feasible_count": feas_count,
            "infeasible_count": TOTAL_N - feas_count,
            "failed_eda_runtime_s": cum_failed_rt,
            "total_eda_runtime_s": cum_total_rt,
            "optimizer_overhead_s": overhead_total,
            "replay_wall_s": trace_wall,
            "fallback_uses": fallback_uses,
            "final_physical_metrics": final_metrics,
        },
    }


def summarize(traces: list[dict]) -> dict:
    per_seed_winners: dict[str, list[str]] = {}
    for seed in SEEDS:
        group = [t for t in traces if t["seed"] == seed]
        scored = [(t["summary"]["best_feasible_qor"], t["method"])
                  for t in group
                  if t["summary"]["best_feasible_qor"] is not None]
        if not scored:
            per_seed_winners[str(seed)] = []
            continue
        floor = min(s for s, _ in scored)
        per_seed_winners[str(seed)] = sorted(
            [m for s, m in scored if s == floor])
    win_counts = {m: sum(1 for w in per_seed_winners.values() if m in w)
                  for m in METHODS}
    secondary = {}
    for method in METHODS:
        group = [t["summary"] for t in traces if t["method"] == method]
        bests = [s["best_feasible_qor"] for s in group
                 if s["best_feasible_qor"] is not None]
        secondary[method] = {
            "n_traces": len(group),
            "n_with_feasible": len(bests),
            "mean_best_qor": float(np.mean(bests)) if bests else None,
            "median_best_qor": float(np.median(bests)) if bests else None,
            "mean_feasible_count": float(np.mean(
                [s["feasible_count"] for s in group])),
            "median_feasible_count": float(np.median(
                [s["feasible_count"] for s in group])),
            "mean_first_feasible_call": float(np.mean(
                [s["first_feasible_call"] for s in group
                 if s["first_feasible_call"] is not None])),
            "mean_failed_eda_runtime_s": float(np.mean(
                [s["failed_eda_runtime_s"] for s in group])),
            "median_failed_eda_runtime_s": float(np.median(
                [s["failed_eda_runtime_s"] for s in group])),
            "mean_total_eda_runtime_s": float(np.mean(
                [s["total_eda_runtime_s"] for s in group])),
            "mean_optimizer_overhead_s": float(np.mean(
                [s["optimizer_overhead_s"] for s in group])),
        }
    return {"per_seed_winners": per_seed_winners,
            "win_counts": win_counts, "secondary": secondary}


def main() -> int:
    static_notes = self_check_no_physical_surface()
    ps_before = snapshot_processes()
    assert ps_before.get("eda_count", 0) == 0, \
        f"EDA processes running before replay: {ps_before}"
    pool, outcomes = load_oracle()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    traces = []
    for seed in SEEDS:
        for method in METHODS:
            traces.append(run_trace(seed, method, pool, outcomes))

    # Structural hidden-outcome audit: every trace reveals exactly its own
    # 24 selections, never duplicates, never unselected IDs.
    for trace in traces:
        assert len(trace["selected_ids"]) == TOTAL_N
        assert len(set(trace["selected_ids"])) == TOTAL_N

    summary = summarize(traces)
    ps_after = snapshot_processes()

    payload = {
        "label": "OFFLINE-SEQUENTIAL-REPLAY-36POOL",
        "oracle": str(LEDGER.relative_to(ROOT)),
        "oracle_counts": {"pool_total": 36, "feasible": 6,
                          "distinct_feasible_qor": 2},
        "oracle_best_qor": -0.09306823743826212,
        "oracle_best_ids": ["cb36_002", "cb36_006", "cb36_010"],
        "seeds": list(SEEDS),
        "methods": list(METHODS),
        "budget": {"shared_init": SHARED_INIT_N,
                   "adaptive": ADAPTIVE_N, "total_per_method": TOTAL_N},
        "driver_seeds": "replay seed (matched across methods)",
        "fallback_policy": "shared RF P(feasible) argmax until first "
                           "feasible (identical across methods)",
        "physical_runs_launched": 0,
        "static_guard_notes": static_notes,
        "ps_before": ps_before,
        "ps_after": ps_after,
        "summary": summary,
        "traces": traces,
    }
    (OUT_DIR / "replay_36pool_offline_results.json").write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n")

    with open(OUT_DIR / "per_seed_method_table.csv", "w",
              encoding="utf-8") as handle:
        handle.write("seed,method,best_feasible_qor,first_feasible_call,"
                     "best_qor_call,feasible_count,infeasible_count,"
                     "failed_eda_runtime_s,total_eda_runtime_s,"
                     "optimizer_overhead_s,replay_wall_s,fallback_uses\n")
        for trace in traces:
            s = trace["summary"]
            best = ("" if s["best_feasible_qor"] is None
                    else f"{s['best_feasible_qor']:.9f}")
            handle.write(f"{s['seed']},{s['method']},{best},"
                         f"{s['first_feasible_call']},{s['best_qor_call']},"
                         f"{s['feasible_count']},{s['infeasible_count']},"
                         f"{s['failed_eda_runtime_s']:.3f},"
                         f"{s['total_eda_runtime_s']:.3f},"
                         f"{s['optimizer_overhead_s']:.4f},"
                         f"{s['replay_wall_s']:.4f},{s['fallback_uses']}\n")

    with open(OUT_DIR / "curves_best_qor_vs_evals.csv", "w",
              encoding="utf-8") as handle:
        handle.write("seed,method,call,best_feasible_qor,"
                     "cum_failed_eda_runtime_s,cum_total_eda_runtime_s,"
                     "cum_optimizer_overhead_s\n")
        for trace in traces:
            for call in trace["calls"]:
                best = ("" if call["best_feasible_qor"] is None
                        else f"{call['best_feasible_qor']:.9f}")
                handle.write(
                    f"{trace['seed']},{trace['method']},{call['call']},"
                    f"{best},{call['cum_failed_eda_runtime_s']:.3f},"
                    f"{call['cum_total_eda_runtime_s']:.3f},"
                    f"{call['cum_optimizer_overhead_s']:.4f}\n")

    with open(OUT_DIR / "verification.log", "w",
              encoding="utf-8") as handle:
        handle.write(f"ps_before={json.dumps(ps_before, sort_keys=True)}\n")
        handle.write(f"ps_after={json.dumps(ps_after, sort_keys=True)}\n")
        handle.write(f"static_guard_notes={static_notes}\n")
        handle.write("physical_runs_launched=0\n")
        handle.write(f"data_source={LEDGER.relative_to(ROOT)}\n")

    assert ps_after.get("eda_count", 0) == 0, \
        f"EDA processes after replay: {ps_after}"
    n_calls = len(traces) * TOTAL_N
    print(f"traces={len(traces)} calls_per_trace={TOTAL_N} "
          f"total_selections={n_calls}")
    print(f"winners={json.dumps(summary['per_seed_winners'], sort_keys=True)} "
          f"wins={json.dumps(summary['win_counts'], sort_keys=True)}")
    print(f"physical_runs_launched=0 eda_before={ps_before.get('eda_count')} "
          f"eda_after={ps_after.get('eda_count')}")
    print(f"out={OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
