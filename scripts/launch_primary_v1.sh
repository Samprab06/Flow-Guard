#!/usr/bin/env bash
# Primary benchmark launcher: runs one frozen optimizer method
# (experiments/manifests/primary_benchmark_v1.json) over the frozen pool
# (experiments/pools/pool_15p8_v1.json) at the fixed 15.8 ns clock.
# Same runner/parser/ledger discipline as the hunt launcher.
# EDA runs under .venv/openlane/bin/python; suggestions under .venv/ml/bin/python.
# Never launches more than requested; never overwrites completed records.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CONFIG="${CONFIG:-$ROOT/designs/flowguard_stress/config.2x1.json}"
MANIFEST_FILE="${MANIFEST_FILE:-$ROOT/experiments/manifests/primary_benchmark_v1.json}"
POOL_FILE="${POOL_FILE:-$ROOT/experiments/pools/pool_15p8_v1.json}"
OBJECTIVE_FILE="${OBJECTIVE_FILE:-$ROOT/experiments/objective_qor_v1.json}"
INIT_FILE="${INIT_FILE:-$ROOT/experiments/manifests/primary_init_v1.json}"
METHOD=""
BUDGET="24"
SHARED_FROM=""
NAMESPACE=""
HOURS="5"
DEADLINE=""
RESUME=0
PREFLIGHT_ONLY=0
SAFETY_MARGIN_S=60
TRIAL_TIMEOUT_S=1800
PYTHON=""
MLPYTHON=""

usage() {
  cat <<'USAGE'
Usage: scripts/launch_primary_v1.sh --method NAME [options]

Options:
  --method NAME       Optimizer: random|optuna_tpe|vanilla_bo|flowguard_raw|flowguard_calibrated (required)
  --budget N          Total trials incl. 8 shared init (default: 24)
  --shared-from NS    Reuse NS trials.jsonl as shared init (skip own init runs)
  --namespace ID      Results namespace (default: primary-<method>-v1)
  --hours H           Wall-clock budget (default: 5)
  --deadline TIME     Absolute UTC deadline (ISO-8601, or Unix seconds)
  --resume            Skip trials already recorded in manifest.jsonl
  --preflight-only    Validate inputs without launching trials
  -h, --help          Show this help
USAGE
}

die() { printf '%s [%s] ERROR %s\n' "$(date -u +%FT%TZ)" "${NAMESPACE:-primary}" "$*" >&2; exit 2; }
status() {
  local message=$*
  printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$NAMESPACE" "$message" | tee -a "$STATUS_LOG"
}
mono_ns() { python3 -c 'import time; print(time.monotonic_ns())'; }

while (($#)); do
  case "$1" in
    --method) METHOD=${2:?missing value for --method}; shift 2 ;;
    --budget) BUDGET=${2:?missing value for --budget}; shift 2 ;;
    --shared-from) SHARED_FROM=${2:?missing value for --shared-from}; shift 2 ;;
    --namespace) NAMESPACE=${2:?missing value for --namespace}; shift 2 ;;
    --hours) HOURS=${2:?missing value for --hours}; shift 2 ;;
    --deadline) DEADLINE=${2:?missing value for --deadline}; shift 2 ;;
    --resume) RESUME=1; shift ;;
    --preflight-only) PREFLIGHT_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

case "$METHOD" in
  random|optuna_tpe|vanilla_bo|flowguard_raw|flowguard_calibrated) ;;
  *) die "--method must be one of random|optuna_tpe|vanilla_bo|flowguard_raw|flowguard_calibrated" ;;
esac
[[ -z $NAMESPACE ]] && NAMESPACE="primary-${METHOD}-v1"
[[ -n $NAMESPACE ]] || die "--namespace is required"
[[ $NAMESPACE =~ ^[A-Za-z0-9_.-]+$ ]] || die "namespace contains invalid characters"
[[ $HOURS =~ ^[0-9]+([.][0-9]+)?$ ]] || die "hours must be a positive decimal"
[[ $BUDGET =~ ^[0-9]+$ ]] && (( BUDGET >= 8 )) || die "budget must be an integer >= 8 (8 shared init)"
[[ -f $MANIFEST_FILE ]] || die "benchmark manifest not found: $MANIFEST_FILE"
[[ -f $POOL_FILE ]] || die "pool not found: $POOL_FILE"
[[ -f $OBJECTIVE_FILE ]] || die "objective not found: $OBJECTIVE_FILE"
SHARED_TRIALS=""
if [[ -n $SHARED_FROM ]]; then
  SHARED_TRIALS="$ROOT/results/$SHARED_FROM/trials.jsonl"
  [[ -f $SHARED_TRIALS ]] || die "shared trials not found: $SHARED_TRIALS"
fi

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
  status "preflight: checking repository, runners, pool/manifest/objective, and method"
  for command in git python3 docker; do command -v "$command" >/dev/null || die "missing prerequisite: $command"; done
  git rev-parse --is-inside-work-tree >/dev/null || die "not a git repository"
  [[ -f $CONFIG && -f $ROOT/src/runner.py && -f $ROOT/src/parser.py && -f $ROOT/src/primary_loop.py ]] || die "campaign inputs are incomplete"
  python3 -m json.tool "$CONFIG" >/dev/null || die "invalid base config"
  python3 -m json.tool "$MANIFEST_FILE" >/dev/null || die "invalid benchmark manifest"
  python3 -m json.tool "$POOL_FILE" >/dev/null || die "invalid pool"
  python3 -m json.tool "$OBJECTIVE_FILE" >/dev/null || die "invalid objective"
  [[ -f $INIT_FILE ]] || status "preflight: no init manifest; will use first 8 pool IDs in seeded order"
  PYTHON="$ROOT/.venv/openlane/bin/python"; [[ -x $PYTHON ]] || die "EDA runner missing: $PYTHON"
  "$PYTHON" -m librelane --help >/dev/null || die "LibreLane is unavailable"
  MLPYTHON="$ROOT/.venv/ml/bin/python"; [[ -x $MLPYTHON ]] || die "ML runtime missing: $MLPYTHON"
  "$MLPYTHON" -c "import sklearn, optuna, scipy, numpy" || die "ML runtime lacks sklearn/optuna/scipy/numpy"
  "$PYTHON" - <<'PY' "$CONFIG"
import json, sys
from src.config_schema import validate_config
with open(sys.argv[1], encoding="utf-8") as handle: validate_config(json.load(handle))
PY
  "$MLPYTHON" -m src.primary_loop suggest --method "$METHOD" --pool "$POOL_FILE" \
    --manifest "$MANIFEST_FILE" --call-index 0 >/dev/null || die "pool/manifest verification failed"
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
  python3 - "$TRIALS" "$SUMMARY" "$NAMESPACE" "$METHOD" <<'PY'
import json, pathlib, sys
rows = [json.loads(line) for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
feasible = [r for r in rows if r.get("feasible") is True]
scores = [r["qor"] for r in feasible if isinstance(r.get("qor"), (int, float))]
result = {"namespace": sys.argv[3], "method": sys.argv[4], "trial_count": len(rows),
          "feasible_count": len(feasible),
          "best_qor": min(scores) if scores else None,
          "updated_at": rows[-1].get("finished_at") if rows else None}
pathlib.Path(sys.argv[2]).write_text(json.dumps(result, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
PY
}

preflight
write_status PREFLIGHT_PASSED preflight "method=${METHOD} budget=${BUDGET} budget_s=${BUDGET_S} per_trial_max=${TRIAL_TIMEOUT_S}s"
if (( PREFLIGHT_ONLY )); then status "preflight complete: no trials launched"; exit 0; fi

INIT_IDS=$(python3 - "$INIT_FILE" "$POOL_FILE" <<'PY'
import json, sys
init_path, pool_path = sys.argv[1:]
pool = json.load(open(pool_path, encoding="utf-8"))["candidates"]
try:
    ids = json.load(open(init_path, encoding="utf-8"))["shared_candidate_ids"]
except FileNotFoundError:
    ids = [row["candidate_id"] for row in pool[:8]]
print("\n".join(ids))
PY
)
ADAPTIVE_N=$((BUDGET - $(printf '%s' "$INIT_IDS" | grep -c .)))

suggest_candidate() {
  local call_index=$1 extra=()
  [[ -n $SHARED_TRIALS ]] && extra=(--shared-trials "$SHARED_TRIALS")
  "$MLPYTHON" -m src.primary_loop suggest --method "$METHOD" --pool "$POOL_FILE" \
    --manifest "$MANIFEST_FILE" --trials "$TRIALS" "${extra[@]}" --call-index "$call_index"
}

candidate_knobs() {
  python3 - "$POOL_FILE" "$1" <<'PY'
import json, sys
pool = json.load(open(sys.argv[1], encoding="utf-8"))["candidates"]
row = next(r for r in pool if r["candidate_id"] == sys.argv[2])
print("\t".join(str(row[key]) for key in ("PL_TARGET_DENSITY_PCT", "GPL_CELL_PADDING", "GRT_ADJUSTMENT", "SYNTH_STRATEGY")))
PY
}

run_trial() {
  local candidate_id=$1 call_index=$2 provenance=${3:-null}
  local trial_id="primary-${METHOD}-${candidate_id}"
  local attempt=0
  while completed "$trial_id" 2>/dev/null; do
    attempt=$((attempt + 1)); trial_id="primary-${METHOD}-${candidate_id}-r${attempt}"
  done
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
  IFS=$'\t' read -r density padding adjustment strategy < <(candidate_knobs "$candidate_id")
  mkdir -p "$(dirname "$config")"
  if [[ ! -e $config ]]; then python3 - "$CONFIG" "$config" "$density" "$padding" "$adjustment" "$strategy" <<'PY'
import json, pathlib, sys
source, destination, density, padding, adjustment, strategy = sys.argv[1:]
config = json.loads(pathlib.Path(source).read_text(encoding="utf-8")); base = pathlib.Path(source).parent.resolve()
def resolve(value):
    if isinstance(value, str) and value.startswith("dir::"): return str((base / value[5:]).resolve())
    if isinstance(value, list): return [resolve(item) for item in value]
    if isinstance(value, dict): return {key: resolve(item) for key, item in value.items()}
    return value
config = resolve(config)
config.update({"CLOCK_PERIOD": 15.8, "FP_CORE_UTIL": 30, "PL_TARGET_DENSITY_PCT": int(density),
               "GPL_CELL_PADDING": int(padding), "GRT_ADJUSTMENT": float(adjustment),
               "SYNTH_STRATEGY": strategy})
pdk = config.get("pdk::sky130A", {})
scl = pdk.get("scl::sky130_fd_sc_hd", {}) if isinstance(pdk, dict) else {}
if isinstance(scl, dict): scl["CLOCK_PERIOD"] = 15.8
pathlib.Path(destination).write_text(json.dumps(config, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
PY
  fi
  status "start $trial_id (candidate=$candidate_id) timeout=${timeout}s"
  local runner_status=FAILED parser_status=NO_METRICS metrics_file="" parsed="" feasible=false qor=null
  if "$PYTHON" -m src.runner --trial-id "$trial_id" --config "$config" --timeout "$timeout" --runs-root "$RUNS_ROOT" < /dev/null; then runner_status=SUCCESS; fi
  [[ -d $trial_dir ]] && cp "$config" "$trial_dir/effective_config.json"
  metrics_file=$(find "$trial_dir" -name metrics.json -type f -print -quit 2>/dev/null || true)
  if [[ $runner_status == SUCCESS && -n $metrics_file ]]; then
    if parsed=$(python3 -m src.parser --trial-id "$trial_id" --metrics "$metrics_file" --status "$status_file" --config "$config" --output-root "$trial_dir/aggregate"); then parser_status=PARSED; feasible=$(python3 -c 'import json,sys; print(str(json.loads(sys.argv[1]).get("feasible",False)).lower())' "$parsed"); else parser_status=PARSER_FAILED; fi
  fi
  if [[ $feasible == true && $parser_status == PARSED ]]; then
    qor=$(python3 - "$parsed" "$OBJECTIVE_FILE" <<'PY'
import json, sys
parsed = json.loads(sys.argv[1]); baselines = json.load(open(sys.argv[2], encoding="utf-8"))["baselines"]
crit = 15.8 - float(parsed["setup_ws"] if parsed.get("setup_ws") is not None else parsed["WNS"])
wl = float(parsed["routing_wirelength"] if parsed.get("routing_wirelength") is not None else parsed["wirelength"])
value = (0.5 * (crit - baselines["min_crit_ns"]) / (baselines["max_crit_ns"] - baselines["min_crit_ns"])
         + 0.3 * (wl - baselines["min_wl_um"]) / (baselines["max_wl_um"] - baselines["min_wl_um"])
         + 0.2 * (float(parsed["area"]) - baselines["min_area_um2"]) / (baselines["max_area_um2"] - baselines["min_area_um2"]))
print(json.dumps(value))
PY
)
  fi
  local finished_at; finished_at=$(date -u +%FT%TZ)
  local record; record=$(python3 - "$trial_id" "$candidate_id" "$call_index" "$runner_status" "$parser_status" "$feasible" "$qor" "$finished_at" "$parsed" "$provenance" "$METHOD" <<'PY'
import json, sys
trial, candidate, call_index, runner, parser, feasible, qor, finished, parsed, provenance, method = sys.argv[1:]
row = {"trial_id": trial, "candidate_id": candidate, "method": method, "call_index": int(call_index),
       "runner_status": runner, "parser_status": parser, "feasible": feasible == "true",
       "qor": json.loads(qor), "finished_at": finished, "experiment": "primary_benchmark_v1"}
if parsed: row["metrics"] = json.loads(parsed)
row["provenance"] = json.loads(provenance) if provenance and provenance != "null" else None
print(json.dumps(row, separators=(",", ":"), sort_keys=True))
PY
)
  append_trial "$record"; refresh_summary; write_status RUNNING trial "completed=$trial_id runner=$runner_status parser=$parser_status"; checkpoint
}

CALL_INDEX=0
if [[ -n $SHARED_TRIALS ]]; then
  CALL_INDEX=$(python3 - "$SHARED_TRIALS" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
print(len(rows))
PY
)
  status "shared init: reusing $CALL_INDEX trials from $SHARED_FROM (no own init runs)"
else
  while IFS= read -r candidate_id; do
    [[ -n $candidate_id ]] || continue
    run_trial "$candidate_id" "$CALL_INDEX" null || { [[ $? == 3 ]] && { status "deadline safety stop"; write_status STOPPED sweep deadline; refresh_summary; checkpoint; exit 0; }; die "trial failed unexpectedly"; }
    CALL_INDEX=$((CALL_INDEX + 1))
  done <<< "$INIT_IDS"
fi

for (( step = 0; step < ADAPTIVE_N; step++ )); do
  suggestion=$(suggest_candidate "$CALL_INDEX") || die "suggester failed at call_index=$CALL_INDEX"
  candidate_id=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["candidate_id"])' "$suggestion")
  provenance=$(python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])["provenance"], sort_keys=True))' "$suggestion")
  run_trial "$candidate_id" "$CALL_INDEX" "$provenance" || { [[ $? == 3 ]] && { status "deadline safety stop"; write_status STOPPED sweep deadline; refresh_summary; checkpoint; exit 0; }; die "trial failed unexpectedly"; }
  CALL_INDEX=$((CALL_INDEX + 1))
done
refresh_summary; write_status COMPLETE complete "primary done method=$METHOD trials=$CALL_INDEX"; checkpoint
status "primary complete: method=$METHOD summary=$SUMMARY"
