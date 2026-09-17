#!/usr/bin/env bash
# Clock hunt launcher: runs a frozen config list (experiments/manifests/*.json)
# at one fixed clock. Same runner/parser/ledger discipline as the exhaustive
# launcher. Never launches the optimizer.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CONFIG="${CONFIG:-$ROOT/designs/flowguard_stress/config.2x1.json}"
HUNT="${HUNT:-$ROOT/experiments/manifests/clock_hunt_16ns_v1.json}"
NAMESPACE=""
HOURS="5"
DEADLINE=""
RESUME=0
PREFLIGHT_ONLY=0
SAFETY_MARGIN_S=60
TRIAL_TIMEOUT_S=1800
PYTHON=""

usage() {
  cat <<'USAGE'
Usage: scripts/launch_clock_hunt.sh --namespace ID [options]

Options:
  --namespace ID        Results namespace (required, e.g. clock_hunt_16ns_v1)
  --hunt FILE           Hunt manifest (default: experiments/manifests/clock_hunt_16ns_v1.json)
  --hours H             Wall-clock budget (default: 5)
  --deadline TIME       Absolute UTC deadline (ISO-8601, or Unix seconds)
  --resume              Skip trials already recorded in manifest.jsonl
  --preflight-only      Validate inputs without launching trials
  -h, --help            Show this help
USAGE
}

die() { printf '%s [%s] ERROR %s\n' "$(date -u +%FT%TZ)" "${NAMESPACE:-hunt}" "$*" >&2; exit 2; }
status() {
  local message=$*
  printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$NAMESPACE" "$message" | tee -a "$STATUS_LOG"
}
mono_ns() { python3 -c 'import time; print(time.monotonic_ns())'; }

while (($#)); do
  case "$1" in
    --namespace) NAMESPACE=${2:?missing value for --namespace}; shift 2 ;;
    --hunt) HUNT=${2:?missing value for --hunt}; shift 2 ;;
    --hours) HOURS=${2:?missing value for --hours}; shift 2 ;;
    --deadline) DEADLINE=${2:?missing value for --deadline}; shift 2 ;;
    --resume) RESUME=1; shift ;;
    --preflight-only) PREFLIGHT_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ -n $NAMESPACE ]] || die "--namespace is required"
[[ $NAMESPACE =~ ^[A-Za-z0-9_.-]+$ ]] || die "namespace contains invalid characters"
[[ $HOURS =~ ^[0-9]+([.][0-9]+)?$ ]] || die "hours must be a positive decimal"
[[ -f $HUNT ]] || die "hunt manifest not found: $HUNT"

RESULTS="$ROOT/results/$NAMESPACE"
RUNS_ROOT="$RESULTS/runs"
CONFIG_ROOT="$RESULTS/configs"
MANIFEST="$RESULTS/manifest.jsonl"
TRIALS="$RESULTS/trials.jsonl"
STATUS_LOG="$RESULTS/status.log"
STATUS_JSON="$RESULTS/status.json"
SUMMARY="$RESULTS/summary.json"
mkdir -p "$RUNS_ROOT" "$CONFIG_ROOT"

BUDGET_S=$(python3 - "$HOURS" "$DEADLINE" <<'PY'
import datetime as dt, decimal, sys, time
hours, deadline = sys.argv[1:]
seconds = int(decimal.Decimal(hours) * 3600)
if seconds < 1:
    raise SystemExit("hours must be greater than zero")
if deadline:
    try:
        absolute = float(deadline)
    except ValueError:
        value = deadline.replace("Z", "+00:00")
        absolute = dt.datetime.fromisoformat(value).timestamp()
    seconds = min(seconds, max(0, int(absolute - time.time())))
print(seconds)
PY
)
(( BUDGET_S > SAFETY_MARGIN_S )) || die "deadline leaves no usable trial budget"
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
    with open(path, encoding="utf-8") as handle: record = json.load(handle)
record.update({"namespace": namespace, "state": state, "stage": stage,
               "message": message, "manifest": manifest, "summary": summary,
               "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
fd, temporary = tempfile.mkstemp(prefix=".status.", dir=os.path.dirname(path), text=True)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(record, handle, separators=(",", ":"), sort_keys=True); handle.write("\n")
os.replace(temporary, path)
PY
}

preflight() {
  status "preflight: checking repository, runner/parser, hunt manifest, and config"
  for command in git python3 docker; do command -v "$command" >/dev/null || die "missing prerequisite: $command"; done
  git rev-parse --is-inside-work-tree >/dev/null || die "not a git repository"
  [[ -f $CONFIG && -f $ROOT/src/runner.py && -f $ROOT/src/parser.py ]] || die "campaign inputs are incomplete"
  python3 -m json.tool "$CONFIG" >/dev/null || die "invalid campaign config"
  python3 -m json.tool "$HUNT" >/dev/null || die "invalid hunt manifest"
  PYTHON="$ROOT/.venv/openlane/bin/python"; [[ -x $PYTHON ]] || PYTHON=python3
  "$PYTHON" -m librelane --help >/dev/null || die "LibreLane is unavailable"
  "$PYTHON" - <<'PY' "$CONFIG"
import json, sys
from src.config_schema import validate_config
with open(sys.argv[1], encoding="utf-8") as handle: validate_config(json.load(handle))
PY
}

ensure_jsonl() { [[ -e $1 ]] || : > "$1"; }
ensure_jsonl "$MANIFEST"; ensure_jsonl "$TRIALS"
if (( ! RESUME )) && [[ -s $MANIFEST ]]; then
  die "namespace already contains results; use --resume or choose a new namespace"
fi
completed() {
  python3 - "$MANIFEST" "$1" <<'PY'
import json, sys
path, trial = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    raise SystemExit(0 if any(json.loads(line).get("event") == "trial" and json.loads(line).get("trial_id") == trial for line in handle if line.strip()) else 1)
PY
}

checkpoint() {
  python3 - "$MANIFEST" "$TRIALS" "$STATUS_LOG" <<'PY'
import os, sys
for path in sys.argv[1:]:
    with open(path, "a", encoding="utf-8") as handle: os.fsync(handle.fileno())
PY
}

append_trial() {
  python3 - "$MANIFEST" "$TRIALS" "$1" <<'PY'
import json, os, pathlib, sys
record = json.loads(sys.argv[3]); record["event"] = "trial"
line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
for name in sys.argv[1:3]:
    with pathlib.Path(name).open("a", encoding="utf-8") as handle: handle.write(line); handle.flush(); os.fsync(handle.fileno())
PY
}

refresh_summary() {
  python3 - "$TRIALS" "$SUMMARY" "$NAMESPACE" <<'PY'
import json, pathlib, sys
rows = [json.loads(line) for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
clocks = sorted({r.get("clock_ns") for r in rows if r.get("clock_ns") is not None})
result = {"namespace": sys.argv[3], "expected_trials": len(rows),
          "trial_count": len(rows),
          "clock_counts": {str(clock): sum(r.get("clock_ns") == clock for r in rows) for clock in clocks},
          "updated_at": rows[-1].get("finished_at") if rows else None}
pathlib.Path(sys.argv[2]).write_text(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
PY
}

preflight
write_status PREFLIGHT_PASSED preflight "budget=${BUDGET_S}s per_trial_max=${TRIAL_TIMEOUT_S}s hunt=$(basename "$HUNT")"
if (( PREFLIGHT_ONLY )); then status "preflight complete: no trials launched"; exit 0; fi

HUNT_ROWS=$(python3 - "$HUNT" <<'PY'
import json, sys
hunt = json.load(open(sys.argv[1], encoding="utf-8"))
for entry in hunt["configs"]:
    v = entry["vars"]
    clock = entry.get("clock_ns", hunt.get("clock_ns", 16.0))
    print("\t".join(str(x) for x in (clock, v["FP_CORE_UTIL"], v["PL_TARGET_DENSITY_PCT"],
          v["GPL_CELL_PADDING"], v["GRT_ADJUSTMENT"], v["SYNTH_STRATEGY"], entry.get("trial_suffix", ""))))
PY
)

run_trial() {
  local trial_id=$1 clock=$2 util=$3 density=$4 padding=$5 adjustment=$6 strategy=$7
  local trial_dir="$RUNS_ROOT/trial_$trial_id"
  local config="$CONFIG_ROOT/$trial_id/config.json"
  local status_file="$trial_dir/status.json"
  if (( RESUME )) && completed "$trial_id"; then status "resume: skipping completed $trial_id"; return 0; fi
  [[ ! -e $trial_dir ]] || die "immutable raw trial exists without a completed manifest record: $trial_id"
  if [[ -e $config ]] && (( ! RESUME )); then
    die "immutable effective config already exists without --resume: $trial_id"
  fi
  local remaining=$(( (DEADLINE_NS - $(mono_ns)) / 1000000000 ))
  (( remaining > SAFETY_MARGIN_S )) || return 3
  local timeout=$TRIAL_TIMEOUT_S; (( timeout > remaining - SAFETY_MARGIN_S )) && timeout=$((remaining - SAFETY_MARGIN_S))
  mkdir -p "$(dirname "$config")"
  if [[ ! -e $config ]]; then python3 - "$CONFIG" "$config" "$clock" "$util" "$density" "$padding" "$adjustment" "$strategy" <<'PY'
import json, pathlib, sys
source, destination, clock, util, density, padding, adjustment, strategy = sys.argv[1:]
config = json.loads(pathlib.Path(source).read_text(encoding="utf-8")); base = pathlib.Path(source).parent.resolve()
def resolve(value):
    if isinstance(value, str) and value.startswith("dir::"): return str((base / value[5:]).resolve())
    if isinstance(value, list): return [resolve(item) for item in value]
    if isinstance(value, dict): return {key: resolve(item) for key, item in value.items()}
    return value
config = resolve(config)
clock = float(clock)
config.update({"CLOCK_PERIOD": clock, "FP_CORE_UTIL": int(util), "PL_TARGET_DENSITY_PCT": int(density), "GPL_CELL_PADDING": int(padding), "GRT_ADJUSTMENT": float(adjustment), "SYNTH_STRATEGY": strategy})
pdk = config.get("pdk::sky130A", {})
scl = pdk.get("scl::sky130_fd_sc_hd", {}) if isinstance(pdk, dict) else {}
if isinstance(scl, dict): scl["CLOCK_PERIOD"] = clock
pathlib.Path(destination).write_text(json.dumps(config, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
PY
  fi
  status "start $trial_id timeout=${timeout}s"
  local runner_status=FAILED parser_status=NO_METRICS metrics_file="" parsed="" feasible=false
  if "$PYTHON" -m src.runner --trial-id "$trial_id" --config "$config" --timeout "$timeout" --runs-root "$RUNS_ROOT" < /dev/null; then runner_status=SUCCESS; fi
  [[ -d $trial_dir ]] && cp "$config" "$trial_dir/effective_config.json"
  metrics_file=$(find "$trial_dir" -name metrics.json -type f -print -quit 2>/dev/null || true)
  if [[ $runner_status == SUCCESS && -n $metrics_file ]]; then
    if parsed=$(python3 -m src.parser --trial-id "$trial_id" --metrics "$metrics_file" --status "$status_file" --config "$config" --output-root "$trial_dir/aggregate"); then parser_status=PARSED; feasible=$(python3 -c 'import json,sys; print(str(json.loads(sys.argv[1]).get("feasible",False)).lower())' "$parsed"); else parser_status=PARSER_FAILED; fi
  fi
  local finished_at; finished_at=$(date -u +%FT%TZ)
  local record; record=$(python3 - "$trial_id" "$clock" "$util" "$density" "$padding" "$adjustment" "$strategy" "$runner_status" "$parser_status" "$feasible" "$finished_at" "$parsed" <<'PY'
import json, sys
trial, clock, util, density, padding, adjustment, strategy, runner, parser, feasible, finished, parsed = sys.argv[1:]
row = {"trial_id": trial, "clock_ns": int(float(clock)), "FP_CORE_UTIL": int(util), "PL_TARGET_DENSITY_PCT": int(density), "GPL_CELL_PADDING": int(padding), "GRT_ADJUSTMENT": float(adjustment), "SYNTH_STRATEGY": strategy, "runner_status": runner, "parser_status": parser, "feasible": feasible == "true", "finished_at": finished, "hunt": "clock_hunt_16ns_v1"}
if parsed: row["metrics"] = json.loads(parsed)
print(json.dumps(row, separators=(",", ":"), sort_keys=True))
PY
)
  append_trial "$record"; refresh_summary; write_status RUNNING trial "completed=$trial_id runner=$runner_status parser=$parser_status"; checkpoint
}

while IFS=$'\t' read -r -u 3 clock util density padding adjustment strategy suffix; do
  [[ -n $clock ]] || continue
  strategy_id=${strategy// /_}; adjustment_id=${adjustment/./p}
  clock_id=$(python3 -c 'import sys; print(sys.argv[1].replace(".","p"))' "$clock")
  trial_id="clock${clock_id}-u${util}-d${density}-p${padding}-g${adjustment_id}-s${strategy_id}"
  [[ -n ${suffix:-} ]] && trial_id="${trial_id}-${suffix}"
  run_trial "$trial_id" "$clock" "$util" "$density" "$padding" "$adjustment" "$strategy" || { [[ $? == 3 ]] && { status "deadline safety stop"; write_status STOPPED sweep deadline; refresh_summary; checkpoint; exit 0; }; die "trial failed unexpectedly"; }
done 3<<< "$HUNT_ROWS"
refresh_summary; write_status COMPLETE complete "hunt done"; checkpoint
status "hunt complete: summary=$SUMMARY"
