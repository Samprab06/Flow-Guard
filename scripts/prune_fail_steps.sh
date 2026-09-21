#!/usr/bin/env bash
# Prune bulky intermediate step dirs from TIMING_FAIL trials, keeping all
# evidence required for audit: effective config, status, runner logs,
# aggregate record, final/ outputs, and STA timing report steps.
# Usage: scripts/prune_fail_steps.sh --namespace NS [--dry-run]
set -Euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
NS=""; DRY=0
while (($#)); do case "$1" in
  --namespace) NS=${2:?}; shift 2 ;;
  --dry-run) DRY=1; shift ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac; done
[[ -n $NS ]] || { echo "--namespace required" >&2; exit 2; }
RUNS="results/$NS/runs"
[[ -d $RUNS ]] || { echo "no runs dir: $RUNS" >&2; exit 2; }
prunable() {
  local trial=$1 kept=0 removed=0
  for entry in "$trial"/*; do
    base=$(basename "$entry")
    case "$base" in
      final|aggregate|status.json|runner.stdout.log|runner.stderr.log|effective_config.json|flow.log|warning.log|error.log|resolved.json|tmp) continue ;;
      12-openroad-staprepnr|55-openroad-stapostpnr) continue ;;
    esac
    if [[ -e $entry ]]; then
      if (( DRY )); then echo "would remove: $entry";
      else rm -rf "$entry"; fi
    fi
  done
}
mapfile -t FAILS < <(python3 - "$NS" <<'PY'
import json, sys
ns = sys.argv[1]
rows = [json.loads(l) for l in open(f"results/{ns}/trials.jsonl") if l.strip()]
for r in rows:
    if not r.get("feasible") and (r.get("metrics") or {}).get("failure_stage") == "TIMING_FAIL":
        print(f"results/{ns}/runs/trial_{r['trial_id']}")
PY
)
echo "TIMING_FAIL trials: ${#FAILS[@]}"
for t in "${FAILS[@]}"; do [[ -d $t ]] && prunable "$t"; done
echo "prune done (dry=$DRY)"
