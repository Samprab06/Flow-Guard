#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CONFIG="$ROOT/designs/flowguard_stress/config.2x1.json"
NAMESPACE="pilot_repaired_tile_v1"
TIMEOUT_S=7200
RESUME=0
PREFLIGHT_ONLY=0

usage() {
  cat <<'USAGE'
Usage: scripts/launch_oracle_campaign.sh [--namespace ID] [--resume]
       [--timeout SECONDS] [--preflight-only]

Launch the repaired 2x1 Oracle pilot in safe, middle, aggressive stages.
Completed records are immutable; --resume only skips fully archived trials.
USAGE
}
die() { printf '%s [%s] ERROR %s\n' "$(date -u +%FT%TZ)" "$NAMESPACE" "$*" >&2; exit 2; }
status() {
  local message=$*
  printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$NAMESPACE" "$message" | tee -a "$STATUS_LOG"
}

while (($#)); do
  case "$1" in
    --namespace) NAMESPACE=${2:?missing value for --namespace}; shift 2 ;;
    --resume) RESUME=1; shift ;;
    --timeout) TIMEOUT_S=${2:?missing value for --timeout}; shift 2 ;;
    --preflight-only) PREFLIGHT_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done
[[ $NAMESPACE =~ ^[A-Za-z0-9_.-]+$ ]] || die "namespace contains invalid characters"
[[ $TIMEOUT_S =~ ^[1-9][0-9]*$ ]] || die "timeout must be a positive integer"

RESULTS="$ROOT/results/$NAMESPACE"
CONFIG_ROOT="$RESULTS/configs"
RUNS_ROOT="$RESULTS/runs"
AGGREGATE_ROOT="$RESULTS/aggregates"
MANIFEST="$RESULTS/manifest.csv"
STATUS_LOG="$RESULTS/status.log"
NAMESPACE_STATUS="$RESULTS/status.json"
mkdir -p "$CONFIG_ROOT" "$RUNS_ROOT" "$AGGREGATE_ROOT"

write_namespace_status() {
  local state=$1 stage=$2 failures=$3
  python3 - "$NAMESPACE_STATUS" "$NAMESPACE" "$state" "$stage" "$failures" "$MANIFEST" <<'PY'
import json, os, sys, tempfile
from datetime import datetime, timezone
path, namespace, state, stage, failures, manifest = sys.argv[1:]
record = {}
if os.path.exists(path):
    record = json.loads(open(path, encoding="utf-8").read())
record.update({"namespace": namespace, "state": state, "stage": stage,
              "failures": int(failures), "manifest": manifest,
              "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})
fd, temporary = tempfile.mkstemp(prefix=".status.", dir=os.path.dirname(path), text=True)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(record, handle, indent=2, sort_keys=True); handle.write("\n")
PY
}

preflight() {
  status "preflight: checking repository, pinned environment, runner/parser, and config"
  for command in git python3 docker; do command -v "$command" >/dev/null || die "missing prerequisite: $command"; done
  git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null || die "not a git repository: $ROOT"
  [[ -f $CONFIG && -f $ROOT/src/runner.py && -f $ROOT/src/parser.py ]] || die "pilot inputs are incomplete"
  [[ -f $ROOT/environment/openlane-baseline.env ]] || die "missing pinned LibreLane environment"
  python3 -m json.tool "$CONFIG" >/dev/null || die "invalid pilot JSON"
  docker info >/dev/null 2>&1 || die "Docker daemon is unavailable"
  PYTHON="$ROOT/.venv/openlane/bin/python"; [[ -x $PYTHON ]] || PYTHON=python3
  "$PYTHON" -m librelane --help >/dev/null || die "LibreLane is unavailable"
  "$PYTHON" - <<'PY' "$CONFIG"
import json, sys
from src.config_schema import validate_config
with open(sys.argv[1], encoding="utf-8") as handle: validate_config(json.load(handle))
PY
}

preflight
write_namespace_status PREFLIGHT_PASSED preflight 0
if (( PREFLIGHT_ONLY )); then
  status "preflight complete: no trials launched"
  exit 0
fi
status "campaign start: fixed 20ns clock; budgets safe=3 middle=8 aggressive=16"

PROBES=(
  'safe:30,38,0,0.05,AREA 0' 'safe:30,45,0,0.10,AREA 1' 'safe:35,38,1,0.05,AREA 2'
  'middle:35,45,1,0.10,AREA 0' 'middle:35,52,1,0.15,AREA 1' 'middle:40,45,1,0.10,AREA 2' 'middle:30,52,2,0.10,AREA 1'
  'middle:40,38,0,0.15,AREA 0' 'middle:35,38,2,0.20,AREA 2' 'middle:30,45,2,0.15,AREA 2' 'middle:40,52,0,0.05,AREA 1'
  'aggressive:40,52,2,0.20,AREA 2' 'aggressive:40,52,2,0.15,AREA 1' 'aggressive:40,45,2,0.20,AREA 0' 'aggressive:40,38,2,0.20,AREA 2'
  'aggressive:35,52,2,0.20,AREA 0' 'aggressive:30,52,2,0.20,AREA 1' 'aggressive:40,45,0,0.20,AREA 2' 'aggressive:35,45,2,0.20,AREA 1'
  'aggressive:30,38,2,0.15,AREA 0' 'aggressive:40,38,1,0.20,AREA 1' 'aggressive:35,52,0,0.20,AREA 2' 'aggressive:30,45,2,0.20,AREA 0'
  'aggressive:40,52,1,0.20,AREA 1' 'aggressive:35,38,2,0.15,AREA 0' 'aggressive:30,52,1,0.20,AREA 2' 'aggressive:40,38,2,0.15,AREA 1'
)
SEEDS=(1101 1102 1103 1201 1202 1203 1204 1205 1206 1207 1208 1301 1302 1303 1304 1305 1306 1307 1308 1309 1310 1311 1312 1313 1314 1315 1316)
(( ${#PROBES[@]} == 27 && ${#SEEDS[@]} == 27 )) || die "internal staged budget mismatch"

python3 - "$MANIFEST" <<'PY'
import csv, os, sys
path = sys.argv[1]
fields = ("trial_id", "stage", "seed", "probe", "status_file", "metrics_file", "runner_status",
          "parser_status", "config_sha256", "effective_config_sha256", "source_tree_sha256",
          "environment_sha256", "parsed_record")
if not os.path.exists(path):
    with open(path, "w", newline="", encoding="utf-8") as handle: csv.writer(handle).writerow(fields)
elif next(csv.reader(open(path, newline="", encoding="utf-8")), []) != list(fields):
    raise SystemExit("manifest header is incompatible; refusing to overwrite it")
PY

manifest_completed() {
  python3 - "$MANIFEST" "$1" "$2" <<'PY'
import csv, sys
path, trial, status = sys.argv[1:]
with open(path, newline="", encoding="utf-8") as handle:
    rows = [row for row in csv.DictReader(handle) if row.get("trial_id") == trial]
raise SystemExit(0 if rows and rows[-1].get("parser_status") == "PARSED" and status == "SUCCESS" else 1)
PY
}

find_metrics() {
  python3 - "$1" <<'PY'
import os, sys
root = sys.argv[1]; found = []; errors = []
def onerror(error): errors.append(str(error))
for directory, _, names in os.walk(root, onerror=onerror):
    for name in names:
        if name == "metrics.json": found.append(os.path.join(directory, name))
if errors: print("; ".join(errors), file=sys.stderr); raise SystemExit(2)
if len(found) != 1: raise SystemExit(1)
print(found[0])
PY
}

archive_trial() {
  python3 - "$1" "$2" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
trial, config = map(Path, sys.argv[1:])
effective = trial / "effective_config.json"
if not effective.exists(): effective.write_bytes(config.read_bytes())
artifacts = []
for path in sorted(p for p in trial.rglob("*") if p.is_file() and p.name != "artifact_manifest.json"):
    artifacts.append({"path": str(path.relative_to(trial)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size": path.stat().st_size})
(trial / "artifact_manifest.json").write_text(json.dumps({"trial_id": trial.name.removeprefix("trial_"), "artifacts": artifacts}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

failures=0
for index in "${!PROBES[@]}"; do
  item=${PROBES[$index]}; stage=${item%%:*}; probe=${item#*:}
  trial_id="${stage}-$(printf '%02d' "$((index + 1))")"
  trial_dir="$RUNS_ROOT/trial_$trial_id"; status_file="$trial_dir/status.json"
  if [[ $RESUME == 1 && -f $status_file ]]; then
    runner_status=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("terminal_status", ""))' "$status_file")
    if manifest_completed "$trial_id" "$runner_status"; then status "resume: skipping completed $trial_id"; continue; fi
    status "gate failed: incomplete record cannot be resumed for $trial_id"; exit 1
  fi
  [[ ! -e $trial_dir ]] || { status "gate failed: immutable artifact exists for $trial_id"; exit 1; }
  trial_config="$CONFIG_ROOT/$trial_id/config.json"; mkdir -p "$(dirname "$trial_config")"
  python3 - "$CONFIG" "$trial_config" "$probe" <<'PY'
import json, pathlib, sys
source, destination, raw = sys.argv[1:]; parts = raw.split(',')
util, density, padding, adjustment, strategy = int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3]), parts[4].strip('"')
config = json.loads(pathlib.Path(source).read_text(encoding='utf-8')); base_dir = pathlib.Path(source).parent.resolve()
def resolve(value):
    if isinstance(value, str) and value.startswith('dir::'): return str((base_dir / value.removeprefix('dir::')).resolve())
    if isinstance(value, list): return [resolve(item) for item in value]
    if isinstance(value, dict): return {key: resolve(item) for key, item in value.items()}
    return value
config = resolve(config); config.update({'CLOCK_PERIOD': 20.0, 'FP_CORE_UTIL': util, 'PL_TARGET_DENSITY_PCT': density, 'GPL_CELL_PADDING': padding, 'GRT_ADJUSTMENT': adjustment, 'SYNTH_STRATEGY': strategy})
pathlib.Path(destination).write_text(json.dumps(config, indent=2, sort_keys=True) + '\n', encoding='utf-8')
PY
  status "[$stage] start $trial_id seed=${SEEDS[$index]} probe=$probe"
  runner_status=FAILED
  if "$PYTHON" -m src.runner --trial-id "$trial_id" --config "$trial_config" --timeout "$TIMEOUT_S" --runs-root "$RUNS_ROOT"; then runner_status=SUCCESS; fi
  metrics_file=""; if metrics_file=$(find_metrics "$trial_dir"); then :; else metrics_file=""; fi
  parser_status=NO_METRICS; parsed_record=""
  if [[ -n $metrics_file ]]; then
    if parsed_record=$(python3 -m src.parser --trial-id "$trial_id" --metrics "$metrics_file" --status "$status_file" --config "$trial_config" --output-root "$AGGREGATE_ROOT"); then parser_status=PARSED; else parser_status=PARSER_FAILED; fi
  fi
  archive_trial "$trial_dir" "$trial_config"
  python3 - "$MANIFEST" "$trial_id" "$stage" "${SEEDS[$index]}" "$probe" "$status_file" "$metrics_file" "$runner_status" "$parser_status" "$parsed_record" <<'PY'
import csv, hashlib, json, sys
manifest, trial, stage, seed, probe, status, metrics, runner, parser, record = sys.argv[1:]
data = json.load(open(status, encoding='utf-8')); row = [trial, stage, seed, probe, status, metrics, runner, parser, data.get('config_sha256',''), data.get('effective_config_sha256',''), data.get('metadata',{}).get('source_tree_sha256',''), data.get('metadata',{}).get('environment_sha256',''), record]
with open(manifest, 'a', newline='', encoding='utf-8') as handle: csv.writer(handle).writerow(row)
PY
  if [[ $runner_status != SUCCESS || $parser_status != PARSED ]]; then failures=$((failures + 1)); write_namespace_status FAILED "$stage" "$failures"; status "[$stage] gate failed $trial_id runner=$runner_status parser=$parser_status"; exit 1; fi
  status "[$stage] gate passed $trial_id"; write_namespace_status RUNNING "$stage" "$failures"
  if [[ $stage == safe && $index == 2 ]]; then status "safe gate passed: final metrics archived; advancing"; fi
done
write_namespace_status COMPLETE complete "$failures"
status "campaign complete: failures=$failures manifest=$MANIFEST"
(( failures == 0 )) || exit 1
