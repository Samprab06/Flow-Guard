#!/usr/bin/env bash
# Run the baseline through LibreLane's supported Docker wrapper.
set -euo pipefail

root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
# shellcheck source=environment/openlane-baseline.env
source "$root/environment/openlane-baseline.env"

[ "$#" -le 1 ] || { printf '%s\n' "Usage: $0 [design-name]" >&2; exit 2; }
command -v docker >/dev/null || { printf '%s\n' 'Docker is required to run LibreLane.' >&2; exit 1; }

design="${1:-flowguard_counter}"
case "$design" in
  ''|*[!a-zA-Z0-9_-]*)
    printf '%s\n' "Invalid design name: $design" >&2
    exit 2
    ;;
esac
design_dir="$root/designs/$design"
config="$design_dir/config.json"
venv_python="$root/.venv/openlane/bin/python"
[ -f "$config" ] || { printf '%s\n' "Missing design config: $config" >&2; exit 1; }
[ -x "$venv_python" ] || { printf '%s\n' 'Run scripts/openlane-setup.sh first.' >&2; exit 1; }
[ -d "$PDK_ROOT" ] || { printf '%s\n' "PDK root is unavailable: $PDK_ROOT" >&2; exit 1; }
docker image inspect "$LIBRELANE_CONTAINER_IMAGE" >/dev/null

run_tag="$design-$(date -u +%Y%m%dT%H%M%S%NZ)-$$"
"$venv_python" -m librelane \
  --docker-no-tty --dockerized --pdk-root "$PDK_ROOT" \
  --pdk "$PDK" --scl "$STD_CELL_LIBRARY" --run-tag "$run_tag" "$config"

printf '%s\n' "LibreLane run output: $design_dir/runs/$run_tag"
