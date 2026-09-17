#!/usr/bin/env bash
# Run this script on the provisioned remote server, or use --host to invoke it there.
# It appends, never rewrites, results/server_experiment_manifest.csv.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRIALS=24
TIMEOUT_S=7200
CONFIG=""
DESIGN="flowguard_stress"
EXPERIMENT_ID="server_experiment"
HOST=""
REMOTE_ROOT=""

usage() {
  cat <<'USAGE'
Usage: scripts/launch_server_matrix.sh [options]

Run the frozen 24-trial LibreLane stress matrix headlessly. By default it uses
designs/flowguard_fir/config.json. Each trial has an isolated config and run
directory under results/; terminal outcomes are append-only in the manifest.

Options:
  --config PATH       Base LibreLane JSON config (overrides --design).
  --design NAME       Use designs/NAME/config.json (default: flowguard_stress).
  --timeout SECONDS   Per-trial timeout, positive integer (default: 7200).
  --experiment-id ID  Output namespace for an immutable matrix (default: server_experiment).
  --host USER@HOST    Execute this same launcher through SSH on the server.
  --remote-root PATH  Repository path on --host (required with --host).
  -h, --help          Show this help.

Examples:
  scripts/launch_server_matrix.sh
  scripts/launch_server_matrix.sh --design flowguard_counter --timeout 3600
  scripts/launch_server_matrix.sh --host user@server --remote-root /srv/flow-guard
USAGE
}

die() { printf 'launch_server_matrix: %s\n' "$*" >&2; exit 2; }

while (($#)); do
  case "$1" in
    --config) CONFIG=${2:?missing value for --config}; shift 2 ;;
    --design) DESIGN=${2:?missing value for --design}; shift 2 ;;
    --timeout) TIMEOUT_S=${2:?missing value for --timeout}; shift 2 ;;
    --experiment-id) EXPERIMENT_ID=${2:?missing value for --experiment-id}; shift 2 ;;
    --host) HOST=${2:?missing value for --host}; shift 2 ;;
    --remote-root) REMOTE_ROOT=${2:?missing value for --remote-root}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ $TIMEOUT_S =~ ^[1-9][0-9]*$ ]] || die "--timeout must be a positive integer"
[[ $EXPERIMENT_ID =~ ^[A-Za-z0-9_.-]+$ ]] || die "--experiment-id contains invalid characters"

if [[ -n $HOST ]]; then
  [[ -n $REMOTE_ROOT ]] || die "--remote-root is required with --host"
  [[ -z $CONFIG || $CONFIG != /* ]] || die "--config must be remote-relative when using --host"
  command -v ssh >/dev/null || die "missing prerequisite: ssh"
  args=(--timeout "$TIMEOUT_S" --experiment-id "$EXPERIMENT_ID")
  [[ -n $CONFIG ]] && args+=(--config "$CONFIG") || args+=(--design "$DESIGN")
  exec ssh -- "$HOST" "cd $(printf '%q' "$REMOTE_ROOT") && exec bash scripts/launch_server_matrix.sh $(printf ' %q' "${args[@]}")"
fi
[[ -z $REMOTE_ROOT ]] || die "--remote-root is only valid with --host"
cd "$ROOT"

[[ -n $CONFIG ]] || CONFIG="$ROOT/designs/$DESIGN/config.json"
[[ $CONFIG = /* ]] || CONFIG="$ROOT/$CONFIG"
CONFIG="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$CONFIG")"

for command in git python3 docker; do command -v "$command" >/dev/null || die "missing prerequisite: $command"; done
git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null || die "repository root is invalid: $ROOT"
[[ -f $CONFIG ]] || die "base config does not exist: $CONFIG"
[[ -f $ROOT/src/runner.py && -f $ROOT/src/parser.py ]] || die "src/runner.py and src/parser.py are required"
[[ -f $ROOT/environment/openlane-baseline.env ]] || die "missing pinned LibreLane environment"
docker info >/dev/null 2>&1 || die "Docker daemon is unavailable (verify headless Docker access)"
PYTHON="$ROOT/.venv/openlane/bin/python"
[[ -x $PYTHON ]] || PYTHON=python3
"$PYTHON" -m librelane --help >/dev/null || die "LibreLane is unavailable to $PYTHON"

RESULTS="$ROOT/results"
MANIFEST="$RESULTS/${EXPERIMENT_ID}_manifest.csv"
CONFIG_ROOT="$RESULTS/${EXPERIMENT_ID}_configs"
RUNS_ROOT="$RESULTS/${EXPERIMENT_ID}_runs"
AGGREGATE_ROOT="$RESULTS/${EXPERIMENT_ID}_aggregates"
LOCK="$RESULTS/.server_experiment.lock"
mkdir -p "$RESULTS" "$CONFIG_ROOT" "$RUNS_ROOT" "$AGGREGATE_ROOT"
mkdir "$LOCK" 2>/dev/null || die "another server matrix launcher is active"
trap 'rmdir "$LOCK"' EXIT

# Frozen candidate order: fixed clock, core utilization, placement density,
# detailed-placement cell padding, global-routing adjustment, synthesis strategy.
# Do not reorder or mutate in place.
CANDIDATES=(
  '20.0,30,38,0,0.05,AREA 0' '20.0,35,45,1,0.10,AREA 1' '20.0,40,52,2,0.15,AREA 2'
  '20.0,30,45,1,0.15,AREA 2' '20.0,35,52,2,0.20,AREA 0' '20.0,40,38,0,0.05,AREA 1'
  '20.0,30,52,2,0.05,AREA 1' '20.0,35,38,0,0.10,AREA 2' '20.0,40,45,1,0.15,AREA 0'
  '20.0,30,38,1,0.20,AREA 0' '20.0,35,45,2,0.05,AREA 1' '20.0,40,52,0,0.10,AREA 2'
  '20.0,30,45,2,0.10,AREA 2' '20.0,35,52,0,0.15,AREA 0' '20.0,40,38,1,0.20,AREA 1'
  '20.0,30,52,0,0.20,AREA 1' '20.0,35,38,1,0.05,AREA 2' '20.0,40,45,2,0.10,AREA 0'
  '20.0,30,38,2,0.15,AREA 0' '20.0,35,45,0,0.20,AREA 1' '20.0,40,52,1,0.05,AREA 2'
  '20.0,30,45,0,0.05,AREA 2' '20.0,35,52,1,0.10,AREA 0' '20.0,40,38,2,0.15,AREA 1'
)
(( ${#CANDIDATES[@]} == TRIALS )) || die "internal frozen-candidate budget is not 24"

for index in "${!CANDIDATES[@]}"; do
  trial_id=$(printf 'server-%02d' "$((index + 1))")
  if [[ -f $MANIFEST ]] && python3 - "$MANIFEST" "$trial_id" <<'PY'
import csv, sys
with open(sys.argv[1], newline='', encoding='utf-8') as handle:
    raise SystemExit(0 if any(row.get('trial_id') == sys.argv[2] for row in csv.DictReader(handle)) else 1)
PY
  then die "trial ID already exists in immutable manifest: $trial_id"; fi
  [[ ! -e $RUNS_ROOT/trial_$trial_id && ! -e $CONFIG_ROOT/$trial_id ]] || die "trial artifacts already exist: $trial_id"
done

append_manifest() {
  local trial_id=$1 candidate=$2 config_path=$3 status_path=$4 metrics_path=$5 parser_status=$6 parsed_record=$7
  python3 - "$MANIFEST" "$trial_id" "$candidate" "$config_path" "$status_path" "$metrics_path" "$parser_status" "$parsed_record" <<'PY'
import csv, os, sys
path, values = sys.argv[1], sys.argv[2:]
fields = ('trial_id', 'candidate', 'config', 'status_file', 'metrics_file', 'parser_status', 'parsed_record')
exists = os.path.exists(path)
if exists:
    with open(path, newline='', encoding='utf-8') as stream:
        if any(row.get('trial_id') == values[0] for row in csv.DictReader(stream)):
            raise SystemExit('refusing to overwrite trial ID: ' + values[0])
with open(path, 'a', newline='', encoding='utf-8') as stream:
    writer = csv.DictWriter(stream, fieldnames=fields)
    if not exists:
        writer.writeheader()
    writer.writerow(dict(zip(fields, values)))
PY
}

failures=0
for index in "${!CANDIDATES[@]}"; do
  trial_id=$(printf 'server-%02d' "$((index + 1))")
  candidate=${CANDIDATES[$index]}
  trial_config="$CONFIG_ROOT/$trial_id/config.json"
  mkdir -p "$(dirname "$trial_config")"
  python3 - "$CONFIG" "$trial_config" "$candidate" <<'PY'
import json, sys
source, destination, candidate = sys.argv[1:]
clock, util, density, pad, grt, strategy = candidate.split(',', 5)
with open(source, encoding='utf-8') as stream:
    config = json.load(stream)
base_dir = __import__('pathlib').Path(source).parent
def resolve_design_relative(value):
    if isinstance(value, str) and value.startswith('dir::'):
        return str((base_dir / value.removeprefix('dir::')).resolve())
    if isinstance(value, list):
        return [resolve_design_relative(item) for item in value]
    if isinstance(value, dict):
        return {key: resolve_design_relative(item) for key, item in value.items()}
    return value
config = resolve_design_relative(config)
config.update({'CLOCK_PERIOD': float(clock), 'FP_CORE_UTIL': int(util),
               'PL_TARGET_DENSITY_PCT': int(density), 'GPL_CELL_PADDING': int(pad),
               'GRT_ADJUSTMENT': float(grt), 'SYNTH_STRATEGY': strategy})
with open(destination, 'x', encoding='utf-8') as stream:
    json.dump(config, stream, indent=2, sort_keys=True)
    stream.write('\n')
PY
  status_file="$RUNS_ROOT/trial_$trial_id/status.json"
  runner_status=CRASH
  if "$PYTHON" -m src.runner --trial-id "$trial_id" --config "$trial_config" --timeout "$TIMEOUT_S" --runs-root "$RUNS_ROOT"; then
    runner_status=SUCCESS
  elif [[ -f $status_file ]]; then
    runner_status=$(python3 -c 'import json,sys; record=json.load(open(sys.argv[1])); print(record.get("terminal_status") or record["status"])' "$status_file")
    failures=$((failures + 1))
  else
    failures=$((failures + 1))
  fi
  metrics_file=""
  shopt -s nullglob globstar
  metrics=("$RUNS_ROOT/trial_$trial_id"/**/final/metrics.json "$RUNS_ROOT/trial_$trial_id"/**/metrics.json)
  shopt -u nullglob globstar
  for candidate_metrics in "${metrics[@]}"; do [[ -f $candidate_metrics ]] && { metrics_file=$candidate_metrics; break; }; done
  parser_status=NO_METRICS
  parsed_record=""
  if [[ -n $metrics_file ]]; then
    if parsed_record=$(python3 -m src.parser --trial-id "$trial_id" --metrics "$metrics_file" --status "$status_file" --config "$trial_config" --output-root "$AGGREGATE_ROOT"); then
      parser_status=PARSED
    else
      parser_status=PARSER_FAILED
      failures=$((failures + 1))
    fi
  fi
  append_manifest "$trial_id" "$candidate" "$trial_config" "$status_file" "$metrics_file" "$runner_status/$parser_status" "$parsed_record"
done

printf 'Completed %d frozen trials; %d non-successful or unparsed. Manifest: %s\n' "$TRIALS" "$failures" "$MANIFEST"
exit 0
