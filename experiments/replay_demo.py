#!/usr/bin/env python3
"""Replay one committed measured decision without starting physical EDA.

This is deliberately a verifier, not an optimizer launcher.  It reads the
frozen evidence bundle and prints the recorded decision and raw
measurement.  No synthesis, placement, routing, STA, DRC, LVS, or signoff
process is imported or started.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "experiments" / "crossbar_v2" / "final_evidence_bundle"
EVIDENCE = BUNDLE / "06_demo.json"
MANIFEST = BUNDLE / "00_MANIFEST.json"
VALIDATION = BUNDLE / "VALIDATION.json"


def load_evidence() -> dict:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    validation = json.loads(VALIDATION.read_text(encoding="utf-8"))
    required = {"command", "decision_record", "result_checks", "layout_image", "separate_runs_note"}
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"evidence missing required fields: {sorted(missing)}")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("git_commit", "")):
        raise ValueError("invalid source revision")
    if not re.fullmatch(r"[0-9a-f]{7,40}", manifest.get("bundle_commit", "")):
        raise ValueError("invalid bundle revision")
    if manifest["frozen_config"]["clock_period_ns"] != 19.9:
        raise ValueError("frozen clock setting changed")
    decision = payload["decision_record"]
    if decision["method"] != "flowguard_calibrated":
        raise ValueError("unexpected optimizer method")
    if decision["selected_id"] not in payload["layout_image"]:
        raise ValueError("selected candidate does not match artifact")
    measurement = payload["result_checks"]
    if not measurement["feasible"] or measurement["drc"] != 0 or not measurement["signoff"]:
        raise ValueError("demo evidence is not a feasible signoff result")
    if not manifest["no_new_runs"] or not validation["no_runs_launched"]:
        raise ValueError("bundle does not certify zero-run evidence assembly")
    payload["manifest"] = manifest
    return payload


def main() -> int:
    evidence = load_evidence()
    settings = evidence["manifest"]["frozen_config"]
    optimizer = evidence["decision_record"]
    result = evidence["result_checks"]
    print("REPLAY: archived measured evidence; physical EDA processes launched: 0")
    print(
        f"REPLAY: source revision {evidence['manifest']['git_commit']}; "
        f"bundle commit {evidence['manifest']['bundle_commit']}"
    )
    print(
        "REPLAY: frozen clock={clock_period_ns} ns, budget={budget}, "
        "method={method}, seed={seed}".format(
            clock_period_ns=settings["clock_period_ns"],
            budget=settings["budget_per_method"],
            method=optimizer["method"],
            seed=optimizer["seed"],
        )
    )
    print(
        "REPLAY: call={call} selected={selected_id} feasible={feasible} "
        "qor={qor} setup_ws={setup_ws} hold_ws={hold_ws} drc={drc} "
        "routing={routing} lvs={lvs} signoff={signoff}".format(
            call=optimizer["call"], selected_id=optimizer["selected_id"], **result
        )
    )
    print(f"REPLAY: frozen evidence {EVIDENCE.relative_to(ROOT)}")
    print(f"REPLAY: artifact {evidence['layout_image']} (separate characterization run)")
    print("FRESH EDA: not run; use the documented OpenLane smoke/run commands for new measurements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
