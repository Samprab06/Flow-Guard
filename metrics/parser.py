"""Parse LibreLane metrics and append immutable trial summaries."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping


ALIASES = {
    "area": ("standard_cell_area", "stdcell_area", "cell_area", "synth_cell_area", "design__instance__area__stdcell", "design__instance__area__stdcell__raw"),
    "WNS": ("setup_wns", "timing__setup__wns", "timing__setup__ws", "wns", "timing__wns", "pl_wns", "optimized_wns", "fastroute_wns", "spef_wns"),
    "TNS": ("setup_tns", "timing__setup__tns", "tns", "timing__tns", "pl_tns", "optimized_tns", "fastroute_tns", "spef_tns"),
    "DRC": ("drc", "drc_count", "drc_violations", "drc__violations", "drc__error__count", "klayout__drc_error__count", "tritonroute_violations", "magic_violations", "klayout_violations", "design__violations"),
    "wirelength": ("wirelength", "wire_length", "total_wirelength", "hpwl", "route__wirelength", "route__wire_length", "routing__wirelength", "design__wirelength"),
    "status": ("status", "flow_status", "flow__status", "run_status", "meta__status"),
}
KNOBS = ("CLOCK_PERIOD", "FP_CORE_UTIL", "PL_TARGET_DENSITY", "CELL_PAD", "GRT_ADJUSTMENT", "SYNTH_STRATEGY")
KNOBS += ("GPL_CELL_PADDING", "PL_TARGET_DENSITY_PCT")

_FAILURE_ORDER = ("PRECHECK_FAIL", "SYNTHESIS_FAIL", "PLACEMENT_FAIL", "CTS_FAIL",
                  "TIMING_FAIL", "ROUTING_FAIL", "DRC_FAIL", "LVS_FAIL",
                  "TIMEOUT", "TOOL_CRASH", "MISSING_METRICS")


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {prefix.lower(): value} if prefix else {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}__{key}" if prefix else str(key)
        if isinstance(item, Mapping):
            result.update(_flatten(item, name))
        else:
            result[name.lower()] = item
    return result


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _canonical_status(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).upper()
    if text in {"SUCCESS", "COMPLETED", "COMPLETE", "PASSED", "PASS", "FLOW_COMPLETED"}:
        return "SUCCESS"
    if "TIMEOUT" in text:
        return "TIMEOUT"
    if text in {"CRASH", "FAILED", "FAIL", "ERROR"}:
        return "CRASH"
    return text


def _first(flat: Mapping[str, Any], *aliases: str) -> Any:
    return next((flat[name.lower()] for name in aliases if name.lower() in flat), None)


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in {"1", "TRUE", "YES", "PASS", "PASSED", "OK", "SUCCESS", "CLEAN"}:
        return True
    if text in {"0", "FALSE", "NO", "FAIL", "FAILED", "ERROR", "DIRTY"}:
        return False
    return None


def _failure_stage(result: Mapping[str, Any], explicit: str | None = None) -> str | None:
    candidates: set[str] = set()
    if explicit:
        candidates.add(str(explicit).upper())
    if result.get("status") == "TIMEOUT":
        candidates.add("TIMEOUT")
    if result.get("status") in {"CRASH", "ERROR"}:
        candidates.add("TOOL_CRASH")
    setup_slack = result.get("setup_ws") if result.get("setup_ws") is not None else result.get("setup_wns")
    hold_slack = result.get("hold_ws") if result.get("hold_ws") is not None else result.get("hold_wns")
    if setup_slack is not None and setup_slack < 0:
        candidates.add("TIMING_FAIL")
    if hold_slack is not None and hold_slack < 0:
        candidates.add("TIMING_FAIL")
    if result.get("routing_overflow") is not None and result["routing_overflow"] > 0:
        candidates.add("ROUTING_FAIL")
    if result.get("routing_completion") is not None and result["routing_completion"] < 100:
        candidates.add("ROUTING_FAIL")
    if result.get("drc_violations") is not None and result["drc_violations"] > 0:
        candidates.add("DRC_FAIL")
    if result.get("lvs_passed") is False:
        candidates.add("LVS_FAIL")
    if result.get("missing_metrics"):
        candidates.add("MISSING_METRICS")
    return min(candidates, key=_FAILURE_ORDER.index) if candidates else None


def _report_evidence(metrics_path: str | Path, result: dict[str, Any]) -> None:
    """Fill routing/LVS/signoff fields from preserved LibreLane reports."""
    path = Path(metrics_path)
    if path.parent.name != "final":
        return
    run_root = path.parent.parent
    route_dirs = list(run_root.glob("*-openroad-detailedrouting"))
    if result.get("routing_completion") is None and route_dirs:
        result["routing_completion"] = 100

    if result.get("lvs_passed") is None:
        reports = list(run_root.glob("*-netgen-lvs/reports/lvs.netgen.rpt"))
        if reports:
            text = reports[0].read_text(encoding="utf-8", errors="replace")
            result["lvs_passed"] = "Final result:" in text and "Circuits match uniquely" in text

    if result.get("signoff_passed") is None:
        reports = list(run_root.glob("*-misc-reportmanufacturability/manufacturability.rpt"))
        reports += list(run_root.glob("*-misc-reportmanufacturability/*.log"))
        if reports:
            text = reports[0].read_text(encoding="utf-8", errors="replace")
            lvs_passed = "* LVS" in text and "Passed" in text
            drc_passed = "* DRC" in text and "Passed" in text
            if result.get("lvs_passed") is None:
                result["lvs_passed"] = lvs_passed
            result["signoff_passed"] = lvs_passed and drc_passed and result.get("drc_violations") == 0


def parse_metrics(metrics_path: str | Path, status_path: str | Path | None = None) -> dict[str, Any]:
    """Extract normalized QoR metrics from flat or nested OpenLane JSON."""
    raw = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    flat = _flatten(raw)
    result: dict[str, Any] = {}
    for field, aliases in ALIASES.items():
        value = next((flat[alias.lower()] for alias in aliases if alias.lower() in flat), None)
        result[field] = _canonical_status(value) if field == "status" else _number(value)
    result.update({
        "setup_ws": _number(_first(flat, "timing__setup__ws", "setup_ws", "timing_setup_ws")),
        "setup_wns": _number(_first(flat, "timing__setup__wns", "setup_wns", "timing_setup_wns")),
        "setup_tns": _number(_first(flat, "timing__setup__tns", "setup_tns", "timing_setup_tns")),
        "setup_violation_count": _number(_first(flat, "timing__setup__violation_count", "setup_violation_count", "setup_violations", "timing__setup__violations")),
        "hold_ws": _number(_first(flat, "timing__hold__ws", "hold_ws", "timing_hold_ws")),
        "hold_wns": _number(_first(flat, "timing__hold__wns", "hold_wns", "timing_hold_wns")),
        "hold_tns": _number(_first(flat, "timing__hold__tns", "hold_tns", "timing_hold_tns")),
        "hold_violation_count": _number(_first(flat, "timing__hold__violation_count", "hold_violation_count", "hold_violations", "timing__hold__violations")),
        "routing_completion": _number(_first(flat, "routing__completion", "routing_completion", "route__completion", "route_completion")),
        "routing_overflow": _number(_first(flat, "routing__overflow", "routing_overflow", "route__overflow", "route_overflow")),
        "routing_wirelength": _number(_first(flat, "routing__wirelength", "routing_wirelength", "route__wirelength", "route_wirelength", "wirelength")),
        "drc_violations": _number(_first(flat, "drc__violations", "drc_violations", "drc_count", "drc__error__count", "klayout__drc_error__count", "klayout_violations", "magic__drc__violations", "magic_violations", "design__violations")),
        "lvs_passed": _boolean(_first(flat, "lvs_passed", "lvs__passed", "lvs_pass", "netgen__lvs__passed")),
        "signoff_passed": _boolean(_first(flat, "signoff_passed", "signoff__passed", "signoff_pass")),
    })
    result["wirelength"] = result["routing_wirelength"] if result["routing_wirelength"] is not None else result["wirelength"]
    result["DRC"] = result["drc_violations"] if result["drc_violations"] is not None else result["DRC"]
    # LibreLane's *_wns fields are violation-only and become zero when timing
    # is clean. Use worst slack (WS) for feasibility; retain WNS separately.
    result["WNS"] = result["setup_ws"] if result["setup_ws"] is not None else (
        result["setup_wns"] if result["setup_wns"] is not None else result["WNS"]
    )
    result["TNS"] = result["setup_tns"] if result["setup_tns"] is not None else result["TNS"]
    _report_evidence(metrics_path, result)
    required = ("area", "setup_tns", "hold_tns", "routing_completion",
                "routing_wirelength", "drc_violations", "lvs_passed", "signoff_passed")
    result["missing_metrics"] = [name for name in required if result.get(name) is None]
    if result.get("setup_ws") is None and result.get("setup_wns") is None:
        result["missing_metrics"].append("setup_ws")
    if result.get("hold_ws") is None and result.get("hold_wns") is None:
        result["missing_metrics"].append("hold_ws")
    if status_path:
        runner_record = json.loads(Path(status_path).read_text(encoding="utf-8"))
        runner_status = runner_record.get("terminal_status") or runner_record.get("status")
        result["status"] = _canonical_status(runner_status) or result["status"]
        result["runtime_s"] = _number(runner_record.get("runtime_s"))
        result["failure_stage"] = _failure_stage(result, runner_record.get("failure_stage"))
    else:
        result["failure_stage"] = _failure_stage(result)
    return result


def is_feasible(
    status: str | None,
    drc: float | int | None,
    wns: float | int | None,
    metrics: Mapping[str, Any] | None = None,
) -> bool:
    """Require complete setup/hold, routing, DRC, LVS, and signoff evidence."""
    if status not in {"SUCCESS", "FEASIBLE"} or drc != 0 or wns is None or wns < 0:
        return False
    if metrics is None:
        return True
    if metrics.get("missing_metrics"):
        return False
    hold_slack = metrics.get("hold_ws") if metrics.get("hold_ws") is not None else metrics.get("hold_wns")
    if hold_slack is None or hold_slack < 0:
        return False
    if metrics.get("hold_violation_count") not in (None, 0):
        return False
    if metrics.get("routing_completion") != 100 or metrics.get("routing_overflow") not in (None, 0):
        return False
    return metrics.get("lvs_passed") is True and metrics.get("signoff_passed") is True


def _knobs(config: str | Path | None) -> dict[str, Any]:
    if not config:
        return {}
    value = json.loads(Path(config).read_text(encoding="utf-8"))
    result = {key: value[key] for key in KNOBS if key in value}
    if "PL_TARGET_DENSITY_PCT" not in result and "PL_TARGET_DENSITY" in result:
        result["PL_TARGET_DENSITY_PCT"] = result["PL_TARGET_DENSITY"]
    return result


def append_record(record: Mapping[str, Any], output_root: str | Path) -> None:
    """Append once to JSONL and CSV; existing trial IDs are immutable."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = root / "aggregated.csv", root / "aggregated.jsonl"
    trial_id = str(record["trial_id"])
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            if any(row.get("trial_id") == trial_id for row in csv.DictReader(handle)):
                raise FileExistsError(f"trial already aggregated: {trial_id}")
    fields = [
        "trial_id", "knobs", "feasible", "area", "WNS", "runtime_s",
        "TNS", "DRC", "wirelength", "setup_ws", "setup_wns", "setup_tns",
        "setup_violation_count", "hold_ws", "hold_wns", "hold_tns", "hold_violation_count",
        "routing_completion", "routing_overflow", "routing_wirelength",
        "drc_violations", "lvs_passed", "signoff_passed", "missing_metrics",
        "status", "failure_stage",
    ]
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow({**record, "knobs": json.dumps(record.get("knobs", {}), sort_keys=True),
                         "missing_metrics": json.dumps(record.get("missing_metrics", []))})
    with json_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def build_record(trial_id: str, metrics_path: str | Path, runtime_s: float | None = None,
                 status_path: str | Path | None = None, config: str | Path | None = None) -> dict[str, Any]:
    metrics = parse_metrics(metrics_path, status_path)
    if runtime_s is None and status_path:
        runtime_s = _number(json.loads(Path(status_path).read_text(encoding="utf-8")).get("runtime_s"))
    return {"trial_id": trial_id, "knobs": _knobs(config), "feasible": is_feasible(metrics["status"], metrics["DRC"], metrics["WNS"], metrics), "area": metrics["area"], "WNS": metrics["WNS"], "runtime_s": runtime_s, **metrics}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--status")
    parser.add_argument("--config")
    parser.add_argument("--runtime-s", type=float)
    args = parser.parse_args(argv)
    record = build_record(args.trial_id, args.metrics, args.runtime_s, args.status, args.config)
    append_record(record, args.output_root)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
