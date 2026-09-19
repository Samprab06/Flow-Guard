#!/usr/bin/env python3
"""Isolated sequential characterization launcher for the frozen crossbar v2 36-point pool.

Reads (never modifies): RTL, primary files, objective/bounds/optimizer code,
committed pool + protocol + characterization manifest.
Writes (only): new effective configs under designs/crossbar_datapath_v2/characterization/,
new scripts/manifests/reports/artifacts under experiments/crossbar_v2/.

Flow:
  1. Exact-gate verify the 6 reusable legacy candidates (knob tuple + config sha256
     + frozen_manifest metrics snapshot). Reuse only on full match.
  2. Generate effective configs for the 30 unmeasured candidates from the current
     pinned v2 RTL/clock/footprint/environment (explicit knob values).
  3. Run each unmeasured candidate EXACTLY ONCE through the real frozen
     src.runner.run_trial LibreLane flow, SEQUENTIALLY (concurrency=1) with an
     identical per-trial timeout.
  4. Bank a machine-readable ledger entry per candidate with status, effective
     config/hash, parser record, setup/hold, feasibility, QoR components/frozen
     QoR, wirelength, area, DRC/LVS/signoff, runtime, raw run path, GDS/render.
  5. Sentinel reruns (--sentinels) run ONLY after all 36 first-pass outcomes exist.

No optimizer code is launched. No comparison replay is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.config_schema import effective_config_hash  # noqa: E402
from src.parser import build_record  # noqa: E402
from src.primary_loop import compute_qor  # noqa: E402 frozen formula only
from src.runner import run_trial  # noqa: E402 frozen runner

POOL_PATH = ROOT / "experiments/pools/pool_crossbar_v2_36_v1.json"
CHARMAN_PATH = ROOT / "experiments/crossbar_v2/characterization_manifest_36pool.json"
PROTO36_PATH = ROOT / "experiments/crossbar_v2/eval_protocol_v2_frozen_36pool.json"
FROZEN_PATH = ROOT / "experiments/crossbar_v2/frozen_manifest.json"
CHAR_DIR = ROOT / "designs/crossbar_datapath_v2/characterization"
ART36_DIR = ROOT / "experiments/crossbar_v2/artifacts_36pool"
LEDGER_PATH = ROOT / "experiments/crossbar_v2/char36_results_ledger.json"
REPORT_PATH = ROOT / "experiments/crossbar_v2/char36_REPORT.md"
SENTINEL_PATH = ROOT / "experiments/crossbar_v2/char36_sentinels.json"

TIMEOUT_S = 3600.0
CONCURRENCY = 1
CLOCK_PERIOD_NS = 19.9
BASELINES = {
    "min_crit_ns": 19.891500132283074,
    "max_crit_ns": 21.398575528307965,
    "min_wl_um": 145247.0,
    "max_wl_um": 152234.0,
    "min_area_um2": 36947.9,
    "max_area_um2": 37504.7,
}

# Deterministic sentinels: one feasible legacy knob set, one fresh AREA-2 knob set.
# Rerun under NEW trial ids with identical effective configs; never overwrite first pass.
SENTINELS = [
    {"sentinel_trial_id": "cb36_005_sentinel01", "pool_candidate_id": "cb36_005"},
    {"sentinel_trial_id": "cb36_029_sentinel01", "pool_candidate_id": "cb36_029"},
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def effective_config_for(knobs: dict) -> dict:
    """Current pinned v2 effective config: fixed RTL/clock/footprint/env + explicit knobs."""
    return {
        "CLOCK_PERIOD": CLOCK_PERIOD_NS,
        "CLOCK_PORT": "clk",
        "DESIGN_NAME": "crossbar_datapath_v2",
        "DIE_AREA": [0.0, 0.0, 320.0, 200.0],
        "FP_CORE_UTIL": 30,
        "FP_SIZING": "absolute",
        "GPL_CELL_PADDING": int(knobs["GPL_CELL_PADDING"]),
        "GRT_ADJUSTMENT": float(knobs["GRT_ADJUSTMENT"]),
        "PL_TARGET_DENSITY_PCT": int(knobs["PL_TARGET_DENSITY_PCT"]),
        "SYNTH_STRATEGY": str(knobs["SYNTH_STRATEGY"]),
        "VERILOG_FILES": "dir::../src/crossbar_datapath_v2.sv",
        "pdk::sky130A": {"scl::sky130_fd_sc_hd": {"CLOCK_PERIOD": CLOCK_PERIOD_NS}},
    }


def feasibility_checks(rec: dict) -> dict:
    setup = rec.get("setup_ws")
    hold = rec.get("hold_ws")
    return {
        "runner_success": rec.get("status") in {"SUCCESS", "FEASIBLE"},
        "setup_nonnegative": (setup is not None and setup >= 0),
        "hold_nonnegative": (hold is not None and hold >= 0),
        "hold_violations_zero": rec.get("hold_violation_count") in (None, 0),
        "routing_complete": rec.get("routing_completion") == 100,
        "routing_overflow_zero_or_unreported": rec.get("routing_overflow") in (None, 0),
        "drc_zero": rec.get("drc_violations") == 0,
        "lvs_passed": rec.get("lvs_passed") is True,
        "signoff_passed": rec.get("signoff_passed") is True,
        "missing_metrics_empty": rec.get("missing_metrics") == [],
    }


def qor_parts(setup_ws: float | None, wirelength: float | None, area: float | None) -> dict:
    if setup_ws is None or wirelength is None or area is None:
        return {"critical_delay_ns": None, "crit_norm": None, "wl_norm": None,
                "area_norm": None, "frozen_qor": None}
    crit = CLOCK_PERIOD_NS - float(setup_ws)
    try:
        q = compute_qor(float(area), crit, float(wirelength), BASELINES)
    except Exception:
        q = None
    lo_c, hi_c = BASELINES["min_crit_ns"], BASELINES["max_crit_ns"]
    lo_w, hi_w = BASELINES["min_wl_um"], BASELINES["max_wl_um"]
    lo_a, hi_a = BASELINES["min_area_um2"], BASELINES["max_area_um2"]
    return {
        "critical_delay_ns": crit,
        "crit_norm": (crit - lo_c) / (hi_c - lo_c),
        "wl_norm": (float(wirelength) - lo_w) / (hi_w - lo_w),
        "area_norm": (float(area) - lo_a) / (hi_a - lo_a),
        "frozen_qor": q,
    }


def copy_compact_artifacts(run_dir: Path, candidate_id: str) -> dict:
    ART36_DIR.mkdir(parents=True, exist_ok=True)
    gds_src = run_dir / "final" / "gds" / "crossbar_datapath_v2.gds"
    png_src = run_dir / "final" / "render" / "crossbar_datapath_v2.png"
    gds_dst = ART36_DIR / f"{candidate_id}.gds"
    png_dst = ART36_DIR / f"{candidate_id}.png"
    out = {"gds": None, "render": None}
    if gds_src.is_file():
        if not gds_dst.is_file():
            shutil.copy2(gds_src, gds_dst)
        out["gds"] = str(gds_dst.relative_to(ROOT))
    if png_src.is_file():
        if not png_dst.is_file():
            shutil.copy2(png_src, png_dst)
        out["render"] = str(png_dst.relative_to(ROOT))
    return out


def verify_legacy_gate() -> dict:
    """Exact gate: knob tuple + config file sha256 + frozen_manifest metrics snapshot."""
    man = json.loads(CHARMAN_PATH.read_text())
    frozen = json.loads(FROZEN_PATH.read_text())
    old = {(e["SYNTH_STRATEGY"], e["PL_TARGET_DENSITY_PCT"], e["GPL_CELL_PADDING"],
            e["GRT_ADJUSTMENT"]): e for e in frozen["candidate_pool"]}
    results = {}
    for r in man["reusable_legacy_candidates"]:
        pid = r["pool_candidate_id"]
        key = (r["knobs"]["SYNTH_STRATEGY"], r["knobs"]["PL_TARGET_DENSITY_PCT"],
               r["knobs"]["GPL_CELL_PADDING"], r["knobs"]["GRT_ADJUSTMENT"])
        detail = {"pool_candidate_id": pid, "ok": False, "reasons": []}
        if key not in old:
            detail["reasons"].append("knob-tuple-not-in-legacy-grid")
        else:
            o = old[key]
            if _sha_file(ROOT / r["legacy_config_file"]) != r["legacy_config_sha256"]:
                detail["reasons"].append("config-sha256-mismatch")
            s = r["legacy_metrics_snapshot"]
            snap_ok = (s["setup_ws"] == o["metrics"]["setup_ws"]
                       and s["hold_ws"] == o["metrics"]["hold_ws"]
                       and s["wirelength"] == o["metrics"]["wirelength"]
                       and s["area"] == o["metrics"]["area"]
                       and s["feasible"] == o["feasible"]
                       and s["critical_delay_ns"] == o["critical_delay_ns"])
            if not snap_ok:
                detail["reasons"].append("metrics-snapshot-mismatch")
            if o["candidate_id"] != r["legacy_candidate_id"] or o["trial_id"] != r["legacy_trial_id"]:
                detail["reasons"].append("legacy-id-drift")
            if not detail["reasons"]:
                detail["ok"] = True
                detail["legacy_candidate_id"] = o["candidate_id"]
        results[pid] = detail
    return results


def build_entry(pool_cand: dict, trial_id: str, run_dir: Path, config_path: Path,
                source: str, extra: dict | None = None) -> dict:
    metrics_path = run_dir / "final" / "metrics.json"
    status_path = run_dir / "status.json"
    rec = build_record(trial_id, metrics_path, status_path=status_path, config=config_path)
    checks = feasibility_checks(rec)
    parts = qor_parts(rec.get("setup_ws"), rec.get("wirelength"), rec.get("area"))
    frozen_qor = parts["frozen_qor"] if rec.get("feasible") else None
    art = copy_compact_artifacts(run_dir, pool_cand["candidate_id"])
    runner_meta = {}
    try:
        runner_meta = json.loads(status_path.read_text())
    except Exception:
        pass
    if rec.get("status") == "TIMEOUT":
        status = "TIMEOUT"
    elif rec.get("status") != "SUCCESS":
        status = f"CRASH-{rec.get('failure_stage') or runner_meta.get('terminal_status') or 'UNKNOWN'}"
    else:
        status = "SUCCESS-FEASIBLE" if rec.get("feasible") else "SUCCESS-INFEASIBLE"
    entry = {
        "pool_candidate_id": pool_cand["candidate_id"],
        "pool_index": pool_cand["pool_index"],
        "knobs": {k: pool_cand[k] for k in
                   ("SYNTH_STRATEGY", "PL_TARGET_DENSITY_PCT", "GPL_CELL_PADDING", "GRT_ADJUSTMENT")},
        "source": source,
        "status": status,
        "trial_id": trial_id,
        "raw_run": str(run_dir.relative_to(ROOT)),
        "effective_config": str(config_path.relative_to(ROOT)),
        "effective_config_sha256": _sha_file(config_path),
        "effective_config_content_hash": effective_config_hash(
            json.loads(config_path.read_text())),
        "runtime_s": rec.get("runtime_s"),
        "runner_terminal_status": runner_meta.get("terminal_status"),
        "runner_exit_code": runner_meta.get("exit_code"),
        "failure_stage": rec.get("failure_stage"),
        "parser_record": rec,
        "setup_ws": rec.get("setup_ws"),
        "hold_ws": rec.get("hold_ws"),
        "feasible": bool(rec.get("feasible")),
        "feasibility_checks": checks,
        "wirelength": rec.get("wirelength"),
        "area": rec.get("area"),
        "critical_delay_ns": parts["critical_delay_ns"],
        "qor_components": {"crit_norm": parts["crit_norm"], "wl_norm": parts["wl_norm"],
                           "area_norm": parts["area_norm"]},
        "frozen_qor": frozen_qor,
        "drc_violations": rec.get("drc_violations"),
        "lvs_passed": rec.get("lvs_passed"),
        "signoff_passed": rec.get("signoff_passed"),
        "routing_completion": rec.get("routing_completion"),
        "routing_overflow": rec.get("routing_overflow"),
        "missing_metrics": rec.get("missing_metrics"),
        "gds": art["gds"],
        "render": art["render"],
    }
    if extra:
        entry.update(extra)
    return entry


def run_first_pass() -> dict:
    pool = json.loads(POOL_PATH.read_text())
    man = json.loads(CHARMAN_PATH.read_text())
    started_all = time.monotonic()
    gate = verify_legacy_gate()
    legacy_by_pid = {r["pool_candidate_id"]: r for r in man["reusable_legacy_candidates"]}
    unmeasured = {c["pool_candidate_id"]: c for c in man["unmeasured_candidates"]}
    entries: dict[str, dict] = {}
    reused = 0
    fresh = 0
    # 1) Reused legacy (no EDA launch).
    for pid, detail in gate.items():
        if not detail["ok"]:
            print(f"GATE-FAIL {pid}: {detail['reasons']} -> will treat as UNMEASURED", flush=True)
            continue
        leg = legacy_by_pid[pid]
        pool_cand = next(c for c in pool["candidates"] if c["candidate_id"] == pid)
        run_dir = ROOT / leg["legacy_raw_run"]
        config_path = ROOT / leg["legacy_config_file"]
        entries[pid] = build_entry(pool_cand, leg["legacy_trial_id"], run_dir, config_path,
                                   source="REUSED-VERIFIED-EXACT",
                                   extra={"legacy_candidate_id": leg["legacy_candidate_id"],
                                          "legacy_config_sha256": leg["legacy_config_sha256"]})
        reused += 1
    # Any gate failure falls through to fresh characterization below.
    gate_failed = [pid for pid, d in gate.items() if not d["ok"]]
    # 2) Fresh characterization, sequential, identical timeout, pool_index order.
    cands = sorted(pool["candidates"], key=lambda c: c["pool_index"])
    for cand in cands:
        pid = cand["candidate_id"]
        if pid in entries:
            continue
        knobs = {k: cand[k] for k in
                 ("SYNTH_STRATEGY", "PL_TARGET_DENSITY_PCT", "GPL_CELL_PADDING", "GRT_ADJUSTMENT")}
        cfg = effective_config_for(knobs)
        cfg_path = CHAR_DIR / f"config-cb36-{cand['pool_index']:03d}.json"
        if cfg_path.is_file():
            existing = json.loads(cfg_path.read_text())
            if existing != cfg:
                raise SystemExit(f"REFUSE: existing effective config differs for {pid}: {cfg_path}")
        else:
            cfg_path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")
        trial_id = pid  # deterministic 1:1 mapping; run dir trial_<trial_id>
        run_dir = CHAR_DIR / "runs" / f"trial_{trial_id}"
        t0 = time.monotonic()
        if not (run_dir / "status.json").is_file():
            print(f"[{_utc()}] RUN {pid} idx={cand['pool_index']} knobs={knobs} "
                  f"timeout={TIMEOUT_S}s conc={CONCURRENCY} ...", flush=True)
            res = run_trial(trial_id, cfg_path, TIMEOUT_S)
            print(f"[{_utc()}] DONE {pid} status={res.get('status')} "
                  f"runtime={res.get('runtime_s'):.1f}s", flush=True)
        else:
            print(f"[{_utc()}] SKIP {pid}: existing first-pass run reused "
                  f"(exactly-once; no relaunch)", flush=True)
        entries[pid] = build_entry(cand, trial_id, run_dir, cfg_path,
                                   source="FRESH-EDA-FIRST-PASS",
                                   extra={"launch_s": round(time.monotonic() - t0, 1)})
        fresh += 1
    wall_s = round(time.monotonic() - started_all, 1)
    ledger = {
        "ledger_id": "crossbar_v2_36pool_characterization_v1",
        "pool": "experiments/pools/pool_crossbar_v2_36_v1.json",
        "pool_canonical_hash": json.loads(POOL_PATH.read_text())["canonical_hash"],
        "characterization_manifest": "experiments/crossbar_v2/characterization_manifest_36pool.json",
        "protocol": "experiments/crossbar_v2/eval_protocol_v2_frozen_36pool.json",
        "protocol_id": "crossbar_v2_eval_protocol_frozen_36pool_v1",
        "frozen_manifest": "experiments/crossbar_v2/frozen_manifest.json",
        "objective_id": "qor_v1_crossbar_v2",
        "objective_baselines": BASELINES,
        "feasibility_implementation": "src/parser.py:is_feasible",
        "runner": "src/runner.py:run_trial (frozen)",
        "fixed": {"CLOCK_PERIOD_NS": CLOCK_PERIOD_NS,
                  "DIE_AREA_UM": [0.0, 0.0, 320.0, 200.0],
                  "FP_CORE_UTIL": 30,
                  "RTL": "designs/crossbar_datapath_v2/src/crossbar_datapath_v2.sv",
                  "RTL_SHA256": _sha_file(ROOT / "designs/crossbar_datapath_v2/src/crossbar_datapath_v2.sv")},
        "execution": {"mode": "isolated-sequential", "concurrency": CONCURRENCY,
                      "timeout_s_per_trial": TIMEOUT_S, "optimizer_runs": 0,
                      "comparison_replay": "none"},
        "legacy_gate": gate,
        "gate_failed_treated_as_unmeasured": gate_failed,
        "counts": {"pool_total": 36, "reused_verified": reused, "fresh_first_pass": fresh,
                   "ledger_entries": len(entries)},
        "wall_s": wall_s,
        "finished_at": _utc(),
        "entries": [entries[c["candidate_id"]] for c in sorted(
            json.loads(POOL_PATH.read_text())["candidates"], key=lambda c: c["pool_index"])],
    }
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    write_report(ledger)
    return ledger


def write_report(ledger: dict) -> None:
    feas = sum(1 for e in ledger["entries"] if e["feasible"])
    ok = sum(1 for e in ledger["entries"] if e["status"].startswith("SUCCESS"))
    lines = [
        "# Crossbar v2 36-pool characterization (first pass)",
        "",
        f"Ledger: `experiments/crossbar_v2/char36_results_ledger.json` "
        f"(id={ledger['ledger_id']}, finished={ledger['finished_at']}).",
        f"Pool hash: `{ledger['pool_canonical_hash']}`; "
        f"RTL sha: `{ledger['fixed']['RTL_SHA256']}`.",
        f"Execution: isolated sequential, concurrency={ledger['execution']['concurrency']}, "
        f"timeout={ledger['execution']['timeout_s_per_trial']}s/trial, "
        f"wall={ledger['wall_s']}s. Optimizer runs: 0. Comparison replay: none.",
        f"Counts: total=36, reused-verified-exact={ledger['counts']['reused_verified']}, "
        f"fresh-first-pass={ledger['counts']['fresh_first_pass']}, "
        f"terminal-success={ok}, feasible={feas}.",
        "",
        "| pool_candidate_id | idx | synth | dens | pad | grt | status | feasible | "
        "setup_ws | hold_ws | wl | area | frozen_qor | runtime_s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for e in ledger["entries"]:
        k = e["knobs"]
        lines.append(
            f"| {e['pool_candidate_id']} | {e['pool_index']} | {k['SYNTH_STRATEGY']} | "
            f"{k['PL_TARGET_DENSITY_PCT']} | {k['GPL_CELL_PADDING']} | {k['GRT_ADJUSTMENT']} | "
            f"{e['status']} | {e['feasible']} | {e['setup_ws']} | {e['hold_ws']} | "
            f"{e['wirelength']} | {e['area']} | {e['frozen_qor']} | {e['runtime_s']} |")
    lines += [
        "",
        "Artifacts: compact GDS/PNG per candidate under `experiments/crossbar_v2/artifacts_36pool/` "
        "(tracked); bulky raw runs under `designs/crossbar_datapath_v2/characterization/runs/trial_cb36_*` "
        "(git-ignored). Effective configs: "
        "`designs/crossbar_datapath_v2/characterization/config-cb36-*.json`.",
        "Sentinels: see `experiments/crossbar_v2/char36_sentinels.json` (only after 36 banked).",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def run_sentinels() -> dict:
    if not LEDGER_PATH.is_file():
        raise SystemExit("REFUSE: no first-pass ledger; bank 36 outcomes first.")
    ledger = json.loads(LEDGER_PATH.read_text())
    if len(ledger.get("entries", [])) != 36:
        raise SystemExit(f"REFUSE: ledger has {len(ledger.get('entries', []))} entries, need 36 first.")
    pool = {c["candidate_id"]: c for c in json.loads(POOL_PATH.read_text())["candidates"]}
    out = {"sentinel_ids": [], "records": [], "started_at": _utc(),
           "timeout_s_per_trial": TIMEOUT_S, "concurrency": CONCURRENCY}
    for spec in SENTINELS:
        tid, pid = spec["sentinel_trial_id"], spec["pool_candidate_id"]
        cand = pool[pid]
        knobs = {k: cand[k] for k in
                 ("SYNTH_STRATEGY", "PL_TARGET_DENSITY_PCT", "GPL_CELL_PADDING", "GRT_ADJUSTMENT")}
        cfg = effective_config_for(knobs)
        cfg_path = CHAR_DIR / f"config-sentinel-{tid}.json"
        if cfg_path.is_file():
            if json.loads(cfg_path.read_text()) != cfg:
                raise SystemExit(f"REFUSE: sentinel config differs: {cfg_path}")
        else:
            cfg_path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")
        run_dir = CHAR_DIR / "runs" / f"trial_{tid}"
        if not (run_dir / "status.json").is_file():
            print(f"[{_utc()}] SENTINEL RUN {tid} (knobs of {pid}) ...", flush=True)
            res = run_trial(tid, cfg_path, TIMEOUT_S)
            print(f"[{_utc()}] SENTINEL DONE {tid} status={res.get('status')}", flush=True)
        else:
            print(f"[{_utc()}] SENTINEL SKIP {tid}: already exists (exactly-once)", flush=True)
        entry = build_entry({**cand, "candidate_id": tid, "pool_index": cand["pool_index"]},
                            tid, run_dir, cfg_path, source="SENTINEL-RERUN")
        entry["sentinel_of"] = pid
        out["records"].append(entry)
        out["sentinel_ids"].append(tid)
    out["finished_at"] = _utc()
    SENTINEL_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sentinels", action="store_true",
                    help="run deterministic sentinel reruns only (requires 36 banked)")
    ap.add_argument("--verify-only", action="store_true", help="exact-gate check only, no EDA")
    args = ap.parse_args(argv)
    if args.verify_only:
        print(json.dumps(verify_legacy_gate(), indent=2, sort_keys=True))
        return 0
    if args.sentinels:
        out = run_sentinels()
        print(json.dumps({"sentinels": out["sentinel_ids"],
                          "path": str(SENTINEL_PATH.relative_to(ROOT))}, indent=2))
        return 0
    ledger = run_first_pass()
    print(json.dumps({"ledger": str(LEDGER_PATH.relative_to(ROOT)),
                      "counts": ledger["counts"], "wall_s": ledger["wall_s"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
