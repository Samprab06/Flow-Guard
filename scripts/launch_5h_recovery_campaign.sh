#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CONFIG="$ROOT/designs/flowguard_stress/config.2x1.json"
NAMESPACE="recovery_5h_v1"
HOURS="4.75"
RESUME=0
PREFLIGHT_ONLY=0
SAFETY_MARGIN_S=300

usage() {
  cat <<'USAGE'
Usage: scripts/launch_5h_recovery_campaign.sh [options]

Options:
  --hours H             Wall-clock budget (default: 4.75)
  --namespace ID        Results namespace (default: recovery_5h_v1)
  --resume              Skip immutable trials already in manifest.jsonl
  --preflight-only      Validate inputs and environment without launching
  -h, --help            Show this help

The campaign runs fixed-clock characterization, deterministic boundary
selection, three-repeat configurations, then at most 16 diagnostics. It never
launches the optimizer. Raw runs remain under results/<namespace>/runs/.
USAGE
}

die() { printf '%s [%s] ERROR %s\n' "$(date -u +%FT%TZ)" "$NAMESPACE" "$*" >&2; exit 2; }
status() {
  local message=$*
  printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$NAMESPACE" "$message" | tee -a "$STATUS_LOG"
}
mono_ns() { python3 -c 'import time; print(time.monotonic_ns())'; }

while (($#)); do
  case "$1" in
    --hours) HOURS=${2:?missing value for --hours}; shift 2 ;;
    --namespace) NAMESPACE=${2:?missing value for --namespace}; shift 2 ;;
    --resume) RESUME=1; shift ;;
    --preflight-only) PREFLIGHT_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ $NAMESPACE =~ ^[A-Za-z0-9_.-]+$ ]] || die "namespace contains invalid characters"
[[ $HOURS =~ ^[0-9]+([.][0-9]+)?$ ]] || die "hours must be a positive decimal"

RESULTS="$ROOT/results/$NAMESPACE"
RUNS_ROOT="$RESULTS/runs"
CONFIG_ROOT="$RESULTS/configs"
MANIFEST="$RESULTS/manifest.jsonl"
TRIALS="$RESULTS/trials.jsonl"
STATUS_LOG="$RESULTS/status.log"
STATUS_JSON="$RESULTS/status.json"
SUMMARY="$RESULTS/summary.json"
mkdir -p "$RUNS_ROOT"

BUDGET_S=$(python3 - "$HOURS" <<'PY'
import decimal, sys
value = decimal.Decimal(sys.argv[1]) * 3600
seconds = int(value)
if seconds < 1:
    raise SystemExit("hours must be greater than zero")
print(seconds)
PY
)
START_NS=$(mono_ns)
DEADLINE_NS=$((START_NS + BUDGET_S * 1000000000))

write_status() {
  local state=$1 stage=$2 message=${3:-}
  python3 - "$STATUS_JSON" "$NAMESPACE" "$state" "$stage" "$message" "$MANIFEST" "$SUMMARY" <<'PY'
import json, os, sys, tempfile
from datetime import datetime, timezone
path, namespace, state, stage, message, manifest, summary = sys.argv[1:]
record = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as handle:
        record = json.load(handle)
record.update({"namespace": namespace, "state": state, "stage": stage,
              "message": message, "manifest": manifest, "summary": summary,
              "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
fd, temporary = tempfile.mkstemp(prefix=".status.", dir=os.path.dirname(path), text=True)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(record, handle, indent=2, sort_keys=True); handle.write("\n")
os.replace(temporary, path)
PY
}

preflight() {
  status "preflight: checking repository, runner/parser, and config"
  for command in git python3 docker; do command -v "$command" >/dev/null || die "missing prerequisite: $command"; done
  git rev-parse --is-inside-work-tree >/dev/null || die "not a git repository"
  [[ -f $CONFIG && -f $ROOT/src/runner.py && -f $ROOT/src/parser.py ]] || die "campaign inputs are incomplete"
  python3 -m json.tool "$CONFIG" >/dev/null || die "invalid campaign config"
  PYTHON="$ROOT/.venv/openlane/bin/python"; [[ -x $PYTHON ]] || PYTHON=python3
  "$PYTHON" -m librelane --help >/dev/null || die "LibreLane is unavailable"
  "$PYTHON" - <<'PY' "$CONFIG"
import json, sys
from src.config_schema import validate_config
with open(sys.argv[1], encoding="utf-8") as handle:
    validate_config(json.load(handle))
PY
}

preflight
write_status PREFLIGHT_PASSED preflight "budget=${BUDGET_S}s"
if (( PREFLIGHT_ONLY )); then status "preflight complete: no trials launched"; exit 0; fi

ensure_jsonl() {
  local path=$1
  [[ -e $path ]] || : > "$path"
}
ensure_jsonl "$MANIFEST"
ensure_jsonl "$TRIALS"

completed() {
  python3 - "$MANIFEST" "$1" <<'PY'
import json, sys
path, trial = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
except FileNotFoundError:
    rows = []
raise SystemExit(0 if any(row.get("event") == "trial" and row.get("trial_id") == trial for row in rows) else 1)
PY
}

checkpoint() {
  python3 - "$MANIFEST" "$TRIALS" "$STATUS_JSON" "$SUMMARY" "$STATUS_LOG" <<'PY'
import os, sys
for name in sys.argv[1:]:
    if os.path.exists(name):
        with open(name, "a", encoding="utf-8") as handle:
            handle.flush()
            os.fsync(handle.fileno())
PY
}

refresh_summary() {
  python3 - "$TRIALS" "$SUMMARY" "$NAMESPACE" <<'PY'
import json, pathlib, sys
trials = pathlib.Path(sys.argv[1])
summary = pathlib.Path(sys.argv[2])
namespace = sys.argv[3]
rows = [json.loads(line) for line in trials.read_text(encoding="utf-8").splitlines() if line.strip()]
fixed = [r for r in rows if r.get("stage") == "fixed_clock"]
boundary = None
safe = {int(r["clock_ns"]): r for r in fixed if r.get("profile") == "safe" and r.get("feasible") is True}
for clock in sorted(safe):
    if any(int(r["clock_ns"]) == clock and r.get("profile") == "aggressive" and r.get("feasible") is False for r in fixed):
        boundary = clock
        break
result = {"namespace": namespace, "trial_count": len(rows),
          "fixed_clock_count": len(fixed), "repeat_count": sum(r.get("stage") == "repeatability" for r in rows),
          "diagnostic_count": sum(r.get("stage") == "diagnostic" for r in rows),
          "selected_clock_ns": boundary, "updated_at": rows[-1].get("finished_at") if rows else None}
summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

append_event() {
  python3 - "$MANIFEST" "$TRIALS" "$1" <<'PY'
import json, pathlib, sys
manifest = pathlib.Path(sys.argv[1])
trials = pathlib.Path(sys.argv[2])
raw = sys.argv[3]
record = json.loads(raw)
record["event"] = "trial"
line = json.dumps(record, sort_keys=True)
with manifest.open("a", encoding="utf-8") as handle: handle.write(line + "\n")
with trials.open("a", encoding="utf-8") as handle: handle.write(line + "\n")
PY
}

run_trial() {
  local trial_id=$1 stage=$2 clock=$3 profile=$4 util=$5 density=$6 padding=$7 adjustment=$8 strategy=$9
  local trial_dir="$RUNS_ROOT/trial_$trial_id"
  local config="$CONFIG_ROOT/$trial_id/config.json" status_file="$trial_dir/status.json"
  if (( RESUME )) && completed "$trial_id"; then status "resume: skipping completed $trial_id"; return 0; fi
  if [[ -e $trial_dir ]]; then die "immutable raw trial already exists without a completed manifest record: $trial_id"; fi
  local remaining_ns=$((DEADLINE_NS - $(mono_ns)))
  local remaining=$((remaining_ns / 1000000000))
  (( remaining > SAFETY_MARGIN_S )) || return 3
  local timeout=$((remaining - SAFETY_MARGIN_S)); (( timeout > 7200 )) && timeout=7200
  mkdir -p "$(dirname "$config")"
  python3 - "$CONFIG" "$config" "$clock" "$util" "$density" "$padding" "$adjustment" "$strategy" <<'PY'
import json, pathlib, sys
source, destination, clock, util, density, padding, adjustment, strategy = sys.argv[1:]
config = json.loads(pathlib.Path(source).read_text(encoding="utf-8"))
base = pathlib.Path(source).parent.resolve()
def resolve(value):
    if isinstance(value, str) and value.startswith("dir::"): return str((base / value[5:]).resolve())
    if isinstance(value, list): return [resolve(item) for item in value]
    if isinstance(value, dict): return {key: resolve(item) for key, item in value.items()}
    return value
config = resolve(config)
config.update({"CLOCK_PERIOD": float(clock), "FP_CORE_UTIL": int(util), "PL_TARGET_DENSITY_PCT": int(density),
               "GPL_CELL_PADDING": int(padding), "GRT_ADJUSTMENT": float(adjustment), "SYNTH_STRATEGY": strategy})
pdk = config.get("pdk::sky130A")
if isinstance(pdk, dict):
    scl = pdk.get("scl::sky130_fd_sc_hd")
    if isinstance(scl, dict):
        scl["CLOCK_PERIOD"] = float(clock)
pathlib.Path(destination).write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  status "[$stage] start $trial_id clock=${clock}ns profile=$profile timeout=${timeout}s"
  local runner_status=FAILED metrics_file="" parser_status=NO_METRICS parsed="" feasible=false
  if "$PYTHON" -m src.runner --trial-id "$trial_id" --config "$config" --timeout "$timeout" --runs-root "$RUNS_ROOT"; then runner_status=SUCCESS; fi
  if [[ -d "$trial_dir" ]]; then cp "$config" "$trial_dir/effective_config.json"; fi
  metrics_file=$(find "$trial_dir" -name metrics.json -type f -print -quit 2>/dev/null || true)
  if [[ $runner_status == SUCCESS && -n $metrics_file ]]; then
    if parsed=$(python3 -m src.parser --trial-id "$trial_id" --metrics "$metrics_file" --status "$status_file" --config "$config" --output-root "$trial_dir/aggregate"); then
      parser_status=PARSED
      feasible=$(python3 -c 'import json,sys; print(str(json.loads(sys.argv[1]).get("feasible",False)).lower())' "$parsed")
    else parser_status=PARSER_FAILED; fi
  fi
  local finished_at; finished_at=$(date -u +%FT%TZ)
  local record; record=$(python3 - "$parsed" "$trial_id" "$stage" "$clock" "$profile" "$runner_status" "$parser_status" "$finished_at" "$feasible" <<'PY'
import json, sys
parsed, trial, stage, clock, profile, runner, parser, finished, feasible = sys.argv[1:]
row = {"trial_id": trial, "stage": stage, "clock_ns": int(clock), "profile": profile,
       "runner_status": runner, "parser_status": parser, "feasible": feasible == "true", "finished_at": finished}
if parsed: row["metrics"] = json.loads(parsed)
print(json.dumps(row, sort_keys=True))
PY
)
  append_event "$record"
  refresh_summary
  write_status RUNNING "$stage" "completed=$trial_id runner=$runner_status parser=$parser_status"
  checkpoint
}

# Stable profile knobs intentionally mirror the repaired pilot's safe/middle/aggressive spread.
PROFILES=("safe:30:38:0:0.05:AREA 0" "middle:35:45:1:0.10:AREA 1" "aggressive:40:52:2:0.20:AREA 2")
CLOCKS=(17 15 13 11)
for clock in "${CLOCKS[@]}"; do
  for item in "${PROFILES[@]}"; do
    IFS=: read -r profile util density padding adjustment strategy <<< "$item"
    run_trial "fixed-${clock}-${profile}" fixed_clock "$clock" "$profile" "$util" "$density" "$padding" "$adjustment" "$strategy" || {
      [[ $? == 3 ]] && { status "deadline safety stop before fixed characterization"; write_status STOPPED fixed_clock deadline; refresh_summary; checkpoint; exit 0; }
      die "trial failed unexpectedly";
    }
  done
done

SELECTED_CLOCK=$(python3 - "$TRIALS" <<'PY'
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
for clock in sorted({int(r["clock_ns"]) for r in rows if r.get("stage") == "fixed_clock"}):
    safe = any(r.get("clock_ns") == clock and r.get("profile") == "safe" and r.get("feasible") is True for r in rows)
    aggressive_fail = any(r.get("clock_ns") == clock and r.get("profile") == "aggressive" and r.get("feasible") is False for r in rows)
    if safe and aggressive_fail:
        print(clock); break
else: print("none")
PY
)
status "fixed-clock characterization complete: selected_clock=$SELECTED_CLOCK"
if [[ $SELECTED_CLOCK != none ]]; then
  for repeat in 1 2 3; do
    for item in "${PROFILES[@]}"; do
      IFS=: read -r profile util density padding adjustment strategy <<< "$item"
      run_trial "repeat-${SELECTED_CLOCK}-${profile}-${repeat}" repeatability "$SELECTED_CLOCK" "$profile" "$util" "$density" "$padding" "$adjustment" "$strategy" || {
        [[ $? == 3 ]] && break 2
        die "repeatability trial failed unexpectedly"
      }
    done
  done
  diag=("safe:30:36:0:0.05:AREA 0" "safe:32:40:0:0.05:AREA 1" "middle:34:44:1:0.10:AREA 0" "middle:36:46:1:0.10:AREA 1" "middle:38:48:1:0.15:AREA 2" "aggressive:38:50:2:0.15:AREA 0" "aggressive:40:50:2:0.20:AREA 1" "aggressive:42:54:2:0.20:AREA 2" "safe:28:42:0:0.05:AREA 2" "middle:33:47:1:0.10:AREA 2" "middle:37:51:1:0.15:AREA 0" "aggressive:36:48:2:0.15:AREA 1" "aggressive:39:53:2:0.20:AREA 0" "aggressive:41:55:2:0.20:AREA 1" "middle:35:49:1:0.10:AREA 2" "aggressive:40:56:2:0.20:AREA 2")
  for index in "${!diag[@]}"; do
    IFS=: read -r profile util density padding adjustment strategy <<< "${diag[$index]}"
    run_trial "diagnostic-${SELECTED_CLOCK}-$(printf '%02d' "$((index + 1))")" diagnostic "$SELECTED_CLOCK" "$profile" "$util" "$density" "$padding" "$adjustment" "$strategy" || {
      [[ $? == 3 ]] && break
      die "diagnostic trial failed unexpectedly"
    }
  done
else
  status "no boundary: safe pass plus aggressive failure was not observed"
fi

refresh_summary
write_status COMPLETE complete "selected_clock=$SELECTED_CLOCK"
checkpoint
status "campaign complete: summary=$SUMMARY"
