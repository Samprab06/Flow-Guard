#!/usr/bin/env python3
"""Assemble the compact final evidence bundle from existing artifacts only.

Copies committed replay outputs verbatim, flattens per-evaluation traces to
machine-readable CSV/JSON, builds chart-ready curves preserving empty=inf
best-QoR cells, and writes manifest / parser-audit / demo / facts /
validation files. Launches no EDA or optimizer runs; modifies no RTL or
primary files. Run from the repo root:

  python3 experiments/crossbar_v2/final_evidence_bundle/scripts/assemble_bundle.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / "experiments/crossbar_v2/final_evidence_bundle"
CB = ROOT / "experiments/crossbar_v2"
COMBINED = CB / "replay_36pool_combined13"
OFFLINE = CB / "replay_36pool_offline"
EXT10 = CB / "replay_36pool_ext10"
ORIGINAL_SEEDS = (11, 29, 47)

sys.path.insert(0, str(BUNDLE / "scripts"))
from recompute_aggregates import main as recompute_main  # noqa: E402


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()


def main() -> int:
    BUNDLE.mkdir(parents=True, exist_ok=True)
    (BUNDLE / "02_traces").mkdir(parents=True, exist_ok=True)
    head = git("git rev-parse HEAD")
    status = git("git status --short")

    # ---- verbatim copies of committed replay outputs ----
    verbatim = [
        (COMBINED / "per_seed_method_table.csv", BUNDLE / "01_method_seed_table.csv"),
        (COMBINED / "curves_best_qor_vs_evals.csv", BUNDLE / "02_traces/curves_committed_combined13.csv"),
        (OFFLINE / "curves_best_qor_vs_evals.csv", BUNDLE / "02_traces/curves_committed_offline9.csv"),
        (EXT10 / "curves_best_qor_vs_evals.csv", BUNDLE / "02_traces/curves_committed_ext10.csv"),
        (OFFLINE / "per_seed_method_table.csv", BUNDLE / "02_traces/table_committed_offline9.csv"),
        (EXT10 / "per_seed_method_table.csv", BUNDLE / "02_traces/table_committed_ext10.csv"),
    ]
    manifest_sources = []
    for src, dst in verbatim:
        assert src.exists(), f"missing committed source {src}"
        shutil.copyfile(src, dst)
        manifest_sources.append({"path": str(src.relative_to(ROOT)),
                                 "bundle_copy": str(dst.relative_to(ROOT)),
                                 "sha256": sha256(src), "verbatim": True})

    combined = json.loads((COMBINED / "replay_36pool_combined13_results.json").read_text())
    traces = combined["traces"]
    assert len(traces) == 39, len(traces)

    # ---- per-evaluation traces flattened (936 rows) ----
    trace_rows = []
    for t in traces:
        for c in t["calls"]:
            trace_rows.append({
                "seed": t["seed"], "method": t["method"],
                "cohort": "original" if t["seed"] in ORIGINAL_SEEDS else "extension",
                "call": c["call"], "phase": c.get("phase"),
                "candidate_id": c.get("candidate_id"), "feasible": c.get("feasible"),
                "qor": c.get("qor"),  # null preserved for infeasible
                "best_feasible_qor": c.get("best_feasible_qor"),  # null pre-first-feasible = +inf
                "cum_failed_eda_runtime_s": c.get("cum_failed_eda_runtime_s"),
                "cum_total_eda_runtime_s": c.get("cum_total_eda_runtime_s"),
                "cum_optimizer_overhead_s": c.get("cum_optimizer_overhead_s"),
                "fallback_used": c.get("fallback_used"),
                "p_feas": (c.get("provenance") or {}).get("p_feas"),
                "ei": (c.get("provenance") or {}).get("ei"),
                "calibration_detail": (c.get("provenance") or {}).get("calibration_detail"),
            })
    assert len(trace_rows) == 936, len(trace_rows)
    with (BUNDLE / "02_traces/per_evaluation_traces.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(trace_rows[0].keys()))
        w.writeheader()
        for r in trace_rows:
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
            # empty cell = null/inf preserved (qor null on infeasible;
            # best_feasible_qor null before first feasible = +inf semantics)
    (BUNDLE / "02_traces/per_evaluation_traces.json").write_text(
        json.dumps(trace_rows, indent=1) + "\n")

    # ---- recomputed aggregates + paired diffs (via sibling script) ----
    assert recompute_main(str(BUNDLE)) == 0

    # ---- chart-ready curves: best-QoR vs evals + runtime costs ----
    curves = list(csv.DictReader((COMBINED / "curves_best_qor_vs_evals.csv").open()))
    assert len(curves) == 936, len(curves)
    with (BUNDLE / "04_curves_best_qor_vs_evals.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seed", "cohort", "method", "call", "best_feasible_qor",
                    "best_qor_is_inf", "cum_failed_eda_runtime_s",
                    "cum_total_eda_runtime_s", "cum_optimizer_overhead_s"])
        for r in curves:
            empty = r["best_feasible_qor"].strip() == ""
            w.writerow([r["seed"],
                        "original" if int(r["seed"]) in ORIGINAL_SEEDS else "extension",
                        r["method"], r["call"], r["best_feasible_qor"],
                        str(empty).lower(), r["cum_failed_eda_runtime_s"],
                        r["cum_total_eda_runtime_s"], r["cum_optimizer_overhead_s"]])
    n_inf = sum(1 for r in curves if r["best_feasible_qor"].strip() == "")
    assert n_inf == 96, n_inf  # empty best-QoR cells preserved (= +inf, none feasible yet)

    table = list(csv.DictReader((COMBINED / "per_seed_method_table.csv").open()))
    with (BUNDLE / "04_runtime_costs.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seed", "cohort", "method",
                    "est_seq_eval_cost_failed_eda_s", "est_seq_eval_cost_total_eda_s",
                    "optimizer_overhead_s", "replay_wall_s", "feasible_count",
                    "infeasible_count", "cost_note"])
        for r in table:
            w.writerow([r["seed"],
                        "original" if int(r["seed"]) in ORIGINAL_SEEDS else "extension",
                        r["method"], r["failed_eda_runtime_s"], r["total_eda_runtime_s"],
                        r["optimizer_overhead_s"], r["replay_wall_s"],
                        r["feasible_count"], r["infeasible_count"],
                        "estimated sequential evaluation cost from recorded physical runs; "
                        "optimizer overhead listed separately, not included"])

    # ---- manifest ----
    proto36 = json.loads((CB / "eval_protocol_v2_frozen_36pool.json").read_text())
    manifest = {
        "label": "FINAL-EVIDENCE-BUNDLE-CROSSBAR-V2",
        "git_commit": head,
        "git_status_at_assembly": status,
        "no_new_runs": True, "no_rtl_edits": True, "no_primary_file_edits": True,
        "not_committed": True,
        "frozen_config": {
            "rtl": proto36["frozen_design"]["rtl"],
            "rtl_sha256": "e2848bb40b338e0197162cc58a494a14e73d427c51c02d1b0c2123fac5407d37",
            "clock_period_ns": 19.9, "die_area_um": [0.0, 0.0, 320.0, 200.0],
            "fp_core_util": 30,
            "pool_manifest": "experiments/pools/pool_crossbar_v2_36_v1.json",
            "pool_canonical_hash": proto36["source_pool"]["canonical_hash"],
            "characterization_manifest": "experiments/crossbar_v2/characterization_manifest_36pool.json",
            "oracle_ledger": "experiments/crossbar_v2/char36_results_ledger.json",
            "protocol": "experiments/crossbar_v2/eval_protocol_v2_frozen_36pool.json",
            "budget_per_method": "8 shared init + 16 adaptive = 24",
            "seeds": [11, 29, 47, 101, 103, 107, 109, 113, 127, 131, 137, 139, 149],
            "original_seeds": list(ORIGINAL_SEEDS),
        },
        "environment": proto36["environment"],
        "objective": proto36["objective"],
        "feasibility": {"rule": proto36["feasibility_rule"],
                        "checks": proto36["feasibility_checks"],
                        "implementation": proto36["feasibility_implementation"]},
        "sources": manifest_sources + [
            {"path": "experiments/crossbar_v2/replay_36pool_combined13/"
                     "replay_36pool_combined13_results.json",
             "sha256": sha256(COMBINED / "replay_36pool_combined13_results.json"),
             "note": "39 traces x 24 calls; too large to duplicate, flattened to "
                     "02_traces/per_evaluation_traces.{csv,json}"},
            {"path": "experiments/crossbar_v2/char36_results_ledger.json",
             "sha256": sha256(CB / "char36_results_ledger.json"),
             "note": "36-point physical oracle; 6 feasible, 0 null/inf runtimes"},
        ],
    }
    (BUNDLE / "00_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (BUNDLE / "00_MANIFEST.md").write_text(
        "# Final evidence bundle — manifest\n\n"
        f"- git commit: `{head}` (working tree clean at assembly: "
        f"{'yes' if not status else 'NO — see 00_MANIFEST.json'})\n"
        "- Scope: existing committed/local artifacts only. No EDA or optimizer "
        "runs launched; no RTL/primary-file edits; nothing committed.\n"
        "- Frozen config: RTL `designs/crossbar_datapath_v2/src/crossbar_datapath_v2.sv` "
        "(sha256 `e2848bb4…5407d37`), clock 19.9 ns, die 320x200, FP_CORE_UTIL 30.\n"
        "- Environment: LibreLane 3.0.14, image "
        "`ghcr.io/librelane/librelane@sha256:f91b21d7…8280a30f`, PDK sky130A rev "
        "`8afc8346…78e71`, SCL sky130_fd_sc_hd (source: `environment/openlane-baseline.env`).\n"
        "- Objective `qor_v1_crossbar_v2` (`src/primary_loop.py:compute_qor`): "
        "`0.5*(crit-min)/(max-min) + 0.3*(wl-min)/(max-min) + 0.2*(area-min)/(max-min)`, "
        "weights crit 0.5 / wl 0.3 / area 0.2; baselines min/max over the 6-candidate pilot "
        "pool (crit 19.891500132283074/21.398575528307965 ns, wl 145247/152234 um, "
        "area 36947.9/37504.7 um2).\n"
        "- Feasibility (`src/parser.py:is_feasible`): SUCCESS/FEASIBLE + DRC==0 + "
        "setup_ws>=0 + hold_ws>=0 + hold_vio==0 + routing==100 + overflow==0/null + "
        "LVS + signoff + missing==[].\n"
        "- Primary endpoint: final best feasible QoR under equal 24-call budgets — "
        "3-way tie on all 13 seeds (no evidence of general optimizer superiority).\n"
        "- Runtime sums are estimated sequential evaluation costs from recorded "
        "physical runs; optimizer overhead is listed separately.\n")

    # ---- parser audit ----
    audit = {
        "audit_doc": "experiments/PARSER_AUDIT.md",
        "corrected_precedence": "src/parser.py:164-166 sets WNS = setup_ws if present, "
                                "else setup_wns; violation-only *_wns clamp to 0 when clean, "
                                "so worst slack (WS) is canonical and WNS retained separately",
        "feasibility_impl": "src/parser.py:187-207 (is_feasible); launcher fallback "
                            "src/parser.py:89-90 (setup_ws else setup_wns)",
        "test": "tests/test_parser.py:62-67 "
                "(test_worst_slack_takes_precedence_over_violation_only_wns: "
                "setup_wns==0, setup_ws==3.9 -> WNS==3.9)",
        "ledger": "experiments/crossbar_v2/char36_results_ledger.json retains nested "
                  "parser_record.{WNS, setup_wns, setup_ws}; replay consumes setup_ws / "
                  "frozen QoR, never a clamped WNS",
    }
    (BUNDLE / "05_parser_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    (BUNDLE / "05_parser_audit.md").write_text(
        "# Parser audit evidence\n\n"
        "- Audit doc: `experiments/PARSER_AUDIT.md` (commits `76d0bf0`, `68ab3f3`).\n"
        "- Corrected setup_ws precedence: `src/parser.py:164-166` — `WNS = setup_ws` "
        "if present else `setup_wns`; `*_wns` are violation-only (0 when clean), "
        "so worst slack is canonical. Launcher fallback `src/parser.py:89-90` "
        "(`setup_ws` else `setup_wns`) for critical delay.\n"
        "- Test: `tests/test_parser.py:62-67` verifies positive worst slack (3.9) "
        "takes precedence over zero violation-only WNS.\n"
        "- Ledger `experiments/crossbar_v2/char36_results_ledger.json` stores nested "
        "`parser_record.{WNS, setup_wns, setup_ws}` per candidate; "
        "`experiments/crossbar_v2/replay_36pool_offline.py` + ext10 read only that "
        "ledger and never recompute/clamp timing.\n")

    # ---- authentic demo sequence: seed-11 FlowGuard call 10 -> cb36_002 ----
    t = next(x for x in traces if x["seed"] == 11 and x["method"] == "flowguard_calibrated")
    c10 = next(c for c in t["calls"] if c["call"] == 10)
    led = {e["pool_candidate_id"]: e for e in
           json.loads((CB / "char36_results_ledger.json").read_text())["entries"]}["cb36_002"]
    demo = {
        "command": ".venv/ml/bin/python experiments/crossbar_v2/replay_36pool_offline.py",
        "note": "Cache replay only: reveals committed ledger outcomes for selected IDs; "
                "launches 0 physical runs (verification.log: 0 EDA processes before/after).",
        "config": "designs/crossbar_datapath_v2/characterization/config-cb36-002.json",
        "config_sha256": sha256(ROOT / "designs/crossbar_datapath_v2/characterization/config-cb36-002.json"),
        "knobs": led["knobs"],
        "decision_record": {"seed": 11, "method": "flowguard_calibrated", "call": 10,
                            "phase": "adaptive", "selected_id": "cb36_002",
                            "provenance": c10["provenance"]},
        "result_checks": {"feasible": True, "qor": -0.09306823743826212,
                          "setup_ws": 0.19090329857261953, "hold_ws": 0.133669412655366,
                          "wirelength": 141422, "area": 37314.5,
                          "critical_delay_ns": 19.70909670142738, "drc": 0,
                          "routing": 100, "lvs": True, "signoff": True,
                          "runtime_s": 607.8006902540001,
                          "first_to_best_this_trace": True,
                          "ei_only_same_call": True,
                          "vanilla_same_seed_best_call": 15},
        "layout_image": "experiments/crossbar_v2/artifacts_36pool/cb36_002.png",
        "layout_image_sha256": sha256(CB / "artifacts_36pool/cb36_002.png"),
        "separate_runs_note": "The layout image comes from the earlier banked characterization "
                              "physical run trial_cb36_002 (separate run), NOT from the replay: "
                              "the replay launched zero physical runs and only attached the "
                              "banked metrics/image by candidate ID.",
    }
    (BUNDLE / "06_demo.json").write_text(json.dumps(demo, indent=2) + "\n")
    (BUNDLE / "06_demo.md").write_text(
        "# Authentic demo sequence (one decision, fully traceable)\n\n"
        "- Exact command: `.venv/ml/bin/python experiments/crossbar_v2/replay_36pool_offline.py` "
        "(cache replay; 0 physical runs launched).\n"
        "- Config: `designs/crossbar_datapath_v2/characterization/config-cb36-002.json` "
        f"(sha256 `{demo['config_sha256'][:12]}…`; knobs AREA 0 / d35 / p2 / grt0.2).\n"
        "- Decision record: seed 11, `flowguard_calibrated`, call 10 (adaptive), selects "
        "`cb36_002`; provenance rank 1 of 27 scored, EI 0.0 x p_feas 0.08, RF fallback "
        "`class_counts=[1, 8]`, data_hash `48dfd5aa…`, full record in `06_demo.json` and "
        "committed `replay_36pool_combined13_results.json`.\n"
        "- Result checks: feasible, QoR -0.09306823743826212 (oracle-best), setup_ws "
        "+0.19090329857261953, hold_ws +0.133669412655366, wl 141422 um, area 37314.5 um2, "
        "crit 19.70909670142738 ns, DRC 0, routing 100, LVS/signoff pass, recorded "
        "runtime 607.8006902540001 s. First-to-best on this trace (call 10); EI-only also "
        "call 10; Vanilla same seed needs call 15.\n"
        "- Matching layout image: `experiments/crossbar_v2/artifacts_36pool/cb36_002.png` "
        f"(sha256 `{demo['layout_image_sha256'][:12]}…`).\n"
        "- Separate-runs note: the image is from the earlier banked characterization "
        "physical run `trial_cb36_002` (separate run), NOT from the replay — the replay "
        "launched zero physical runs and only re-attached banked outcomes by ID.\n")

    # ---- facts sheet ----
    facts = {
        "confirmed": {
            "oracle": "36 entries, 6 feasible (cb36_001/002/005/006/009/010), "
                      "2 distinct feasible QoR (-0.09306823743826212 x3 at 002/006/010, "
                      "0.3112996180098017 x3 at 001/005/009)",
            "ledger_runtimes": "all 36 runtime_s finite; 0 null, 0 inf",
            "curves_inf_cells": "96 empty best_feasible_qor cells in combined curves "
                                "(pre-first-feasible = +inf); preserved as empty + flag",
            "primary_endpoint": "final best feasible QoR ties 3-way on all 13 seeds",
            "time_to_best": "FlowGuard == EI-only on all 13 seeds; both beat Vanilla by "
                            "5-6 calls on seeds 11/29/101/131; other 9 seeds decided in shared init",
            "fallback": "pre-feasible RF fallback exercised only on seed 101 (fallback_uses=2, all methods)",
            "fresh_validation": "cb36_002/cb36_006 clean reruns MATCH oracle on all physical metrics; "
                                "runtimes +15.8/+6.8 s wall-clock variance only",
            "pilot_vs_36pool": "pilot (seeds 1337/1339/1340, 6-call, 6-cand pool) is a separate "
                               "protocol from the 36-pool replay; not comparable",
        },
        "unresolved_discrepancies": {
            "qor_display_rounding": "reports print -0.093068237 / 0.311299618 (9dp); "
                                    "JSON/ledger carry full -0.09306823743826212 / 0.3112996180098017",
            "runtime_two_timings": "ledger runtime_s (authoritative, used in sums; e.g. cb36_002 "
                                   "607.8006902540001) vs launch_s (coarse launcher wall, e.g. 607.9)",
            "seed47_init_luck": "best arm cb36_002 sits in shared init (call 8); curves coincide by "
                                "construction, not policy",
            "feasible_count_gap": "Vanilla collects 6.0 feasible/trace vs FlowGuard 4.38 vs EI-only 3.38 "
                                  "yet ties on best QoR — extra feasible arms are QoR-duplicates",
        },
        "source_paths": {
            "oracle": "experiments/crossbar_v2/char36_results_ledger.json",
            "combined_table": "experiments/crossbar_v2/replay_36pool_combined13/per_seed_method_table.csv",
            "combined_curves": "experiments/crossbar_v2/replay_36pool_combined13/curves_best_qor_vs_evals.csv",
            "combined_results": "experiments/crossbar_v2/replay_36pool_combined13/"
                                "replay_36pool_combined13_results.json",
            "offline_report": "experiments/crossbar_v2/replay_36pool_offline/REPORT.md",
            "combined_report": "experiments/crossbar_v2/replay_36pool_combined13/REPORT.md",
            "parser_audit": "experiments/PARSER_AUDIT.md",
            "fresh_validation": "experiments/crossbar_v2/fresh_validation_20260919/",
        },
    }
    (BUNDLE / "07_FACTS.json").write_text(json.dumps(facts, indent=2) + "\n")
    (BUNDLE / "07_FACTS.md").write_text(
        "# Facts sheet — confirmed values, discrepancies, sources\n\n"
        "## Confirmed\n\n"
        "- Oracle: 36 entries, 6 feasible (`cb36_001/002/005/006/009/010`), 2 distinct "
        "feasible QoR values (-0.09306823743826212 x3 at 002/006/010; 0.3112996180098017 x3).\n"
        "- Ledger runtimes: all 36 finite; 0 null, 0 inf. `inf` exists only as 96 empty "
        "best-QoR curve cells (pre-first-feasible = +inf), preserved as empty + flag.\n"
        "- Primary endpoint: final best feasible QoR ties 3-way on all 13 seeds.\n"
        "- Time-to-best: FlowGuard == EI-only on all 13 seeds; both beat Vanilla by 5-6 calls "
        "on seeds 11/29/101/131; 9 seeds decided inside shared init.\n"
        "- Fallback exercised only on seed 101 (`fallback_uses=2`, all methods).\n"
        "- Fresh validation: `cb36_002`/`cb36_006` reruns MATCH oracle on every physical metric; "
        "runtimes +15.8/+6.8 s wall-clock variance only.\n"
        "- Pilot (1337/1339/1340, 6-call, 6-cand pool) is a separate protocol; not comparable "
        "to the 36-pool replay.\n\n"
        "## Unresolved / must-not-overclaim discrepancies\n\n"
        "- QoR display rounding: reports show 9dp; JSON/ledger carry full precision.\n"
        "- Two runtime timings: `runtime_s` (authoritative for sums) vs coarse `launch_s`.\n"
        "- Seed 47 decided by init luck (best arm in shared init, call 8).\n"
        "- Vanilla collects more feasible arms (6.0 vs 4.38 vs 3.38) yet ties on best QoR — "
        "extras are QoR-duplicates.\n\n"
        "## Source paths\n\n"
        "See `07_FACTS.json:source_paths` for exact committed paths.\n")

    # ---- validation ----
    bundle_files = sorted(str(p.relative_to(ROOT)) for p in BUNDLE.rglob("*") if p.is_file())
    validation = {
        "git_commit": head, "git_clean": status == "",
        "row_checks": {"method_seed_table_rows": 39, "trace_rows": len(trace_rows),
                       "curve_rows": len(curves), "inf_cells_preserved": n_inf},
        "recompute": "03 recompute asserts passed (13-seed tie; means 13046.8/14378.0/14994.8; "
                      "paired FG-EI dQoR=0 and dCall=0 on all seeds)",
        "no_runs_launched": True, "no_rtl_or_primary_edits": True, "committed": False,
        "files": bundle_files,
    }
    (BUNDLE / "VALIDATION.json").write_text(json.dumps(validation, indent=2) + "\n")
    (BUNDLE / "VALIDATION.md").write_text(
        "# Validation checks (all must pass)\n\n"
        f"- git commit `{head}`; tree clean: {'yes' if not status else 'NO'}\n"
        "- `01_method_seed_table.csv`: 39 rows (13 seeds x 3 methods), byte-copy of committed combined table.\n"
        "- `02_traces/per_evaluation_traces.csv`: 936 rows (39 x 24); null/inf preserved as empty cells.\n"
        "- `04_curves_best_qor_vs_evals.csv`: 936 rows; 96 empty best-QoR cells (= +inf) preserved with flag.\n"
        "- `03` recompute asserts: 13-seed primary tie; mean failed EDA 13046.8/14378.0/14994.8 s; "
        "paired FlowGuard-minus-EI-only dQoR=0 and dCall=0 on every seed.\n"
        "- Original seeds 11/29/47 labeled via `cohort=original` in all machine-readable outputs.\n"
        "- No EDA/optimizer runs launched; no RTL/primary edits; bundle NOT committed.\n")
    print("bundle assembled:", len(bundle_files), "files")
    for f in bundle_files:
        print(" ", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
