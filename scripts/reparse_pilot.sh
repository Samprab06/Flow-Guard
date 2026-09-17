#!/usr/bin/env bash
# Reparse preserved pilot artifacts without rerunning LibreLane.
set -Eeuo pipefail
IFS=$'\n\t'

root="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
namespace="pilot_repaired_tile_v3"
output_root=""

usage() {
  cat <<'USAGE'
Usage: scripts/reparse_pilot.sh [--namespace ID] [--output-root PATH]

Reparse final metrics from an existing pilot namespace. Raw EDA runs are never
modified or rerun. The default output is a new v3_corrected_aggregates folder.
USAGE
}

while (($#)); do
  case "$1" in
    --namespace) namespace=${2:?missing value for --namespace}; shift 2 ;;
    --output-root) output_root=${2:?missing value for --output-root}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ "$namespace" =~ ^[A-Za-z0-9_.-]+$ ]] || {
  printf 'invalid namespace: %s\n' "$namespace" >&2
  exit 2
}

source_root="$root/results/$namespace"
runs_root="$source_root/runs"
configs_root="$source_root/configs"
manifest_path="$source_root/manifest.csv"
output_root=${output_root:-"$source_root/v3_corrected_aggregates"}
python_bin="$root/.venv/openlane/bin/python"
[[ -x "$python_bin" ]] || python_bin=python3
mkdir -p "$output_root/configs"

[[ -d "$runs_root" ]] || {
  printf 'missing raw run directory: %s\n' "$runs_root" >&2
  exit 1
}
if [[ ! -f "$manifest_path" ]]; then
  printf 'NOTICE: manifest missing; using per-trial configs without probe reconstruction\n'
fi

parsed=0
skipped=0
while IFS= read -r trial_dir; do
  trial_id=${trial_dir##*/trial_}
  status_file="$trial_dir/status.json"
  if [[ ! -f "$status_file" ]]; then
    status_file=""
    while IFS= read -r candidate; do status_file=$candidate; break; done < <(find "$trial_dir" -type f -name status.json -print)
  fi
  config_file="$configs_root/$trial_id/config.json"
  if [[ ! -f "$config_file" ]]; then
    config_file=""
    while IFS= read -r candidate; do config_file=$candidate; break; done < <(find "$trial_dir" -type f -name effective_config.json -print)
  fi
  if [[ -z "$config_file" || ! -f "$config_file" ]]; then
    while IFS= read -r candidate; do config_file=$candidate; break; done < <(find "$trial_dir" -type f -path '*/config.json' -print)
  fi
  if [[ -n "$config_file" && -f "$config_file" ]]; then
    if ! python3 - "$config_file" <<'PY'
import json, sys
config = json.load(open(sys.argv[1], encoding="utf-8"))
required = {"FP_CORE_UTIL", "PL_TARGET_DENSITY_PCT", "GPL_CELL_PADDING", "SYNTH_STRATEGY"}
raise SystemExit(0 if required.intersection(config) else 1)
PY
    then
      while IFS= read -r candidate; do
        if python3 - "$candidate" <<'PY'
import json, sys
config = json.load(open(sys.argv[1], encoding="utf-8"))
required = {"FP_CORE_UTIL", "PL_TARGET_DENSITY_PCT", "GPL_CELL_PADDING", "SYNTH_STRATEGY"}
raise SystemExit(0 if required.intersection(config) else 1)
PY
        then config_file=$candidate; break; fi
      done < <(find "$trial_dir" -type f -path '*/config.json' -print)
    fi
  fi
  metrics_file=""
  while IFS= read -r candidate; do
    metrics_file=$candidate
    break
  done < <(find "$trial_dir" -type f -path '*/final/metrics.json' -print)

  if [[ -z "$metrics_file" || ! -f "$status_file" || ! -f "$config_file" ]]; then
    printf 'SKIP %s (metrics=%s status=%s config=%s)\n' "$trial_id" \
      "${metrics_file:-missing}" "${status_file:-missing}" "${config_file:-missing}"
    skipped=$((skipped + 1))
    continue
  fi

  probe="$(python3 - "$manifest_path" "$trial_id" <<'PY'
import csv, sys
import os
if not os.path.isfile(sys.argv[1]):
    print("")
    raise SystemExit
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    rows = [row for row in csv.DictReader(handle) if row.get("trial_id") == sys.argv[2]]
print(rows[-1].get("probe", "") if rows else "")
PY
)"
  effective_config="$output_root/configs/$trial_id.json"
  python3 - "$config_file" "$effective_config" "$probe" <<'PY'
import json, pathlib, sys
source, destination, probe = sys.argv[1:]
config = json.loads(pathlib.Path(source).read_text(encoding="utf-8"))
parts = [part.strip().strip('"') for part in probe.split(",", 4)] if probe else []
if len(parts) == 5:
    # The manifest probe is stage-independent in this pilot:
    # util,density,padding,adjustment,strategy.
    fields = parts
    config.update({
        "FP_CORE_UTIL": int(fields[0]),
        "PL_TARGET_DENSITY_PCT": int(fields[1]),
        "GPL_CELL_PADDING": int(fields[2]),
        "GRT_ADJUSTMENT": float(fields[3]),
        "SYNTH_STRATEGY": fields[4].strip().strip('"'),
    })
pathlib.Path(destination).write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

  printf 'PARSE %s\n' "$trial_id"
  "$python_bin" -m src.parser \
    --trial-id "$trial_id" \
    --metrics "$metrics_file" \
    --status "$status_file" \
    --config "$effective_config" \
    --output-root "$output_root" >/dev/null
  parsed=$((parsed + 1))
done < <(find "$runs_root" -mindepth 1 -maxdepth 1 -type d -name 'trial_*' -print | sort)

printf 'Reparsed %d trial(s); skipped %d. Output: %s\n' "$parsed" "$skipped" "$output_root"
