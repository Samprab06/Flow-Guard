#!/usr/bin/env bash
# Offline structural validation; --container runs the configured LibreLane flow.
set -euo pipefail

root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
config="$root/designs/flowguard_counter/config.json"
rtl="$root/designs/flowguard_counter/src/tt_um_flowguard_counter.v"

python3 - "$config" "$rtl" <<'PY'
import json
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
rtl_path = pathlib.Path(sys.argv[2])
config = json.loads(config_path.read_text())
required = {
    "DESIGN_NAME": str,
    "VERILOG_FILES": str,
    "CLOCK_PORT": str,
    "CLOCK_PERIOD": (int, float),
    "FP_CORE_UTIL": (int, float),
    "PL_TARGET_DENSITY_PCT": (int, float),
}
for key, expected_type in required.items():
    if key not in config or not isinstance(config[key], expected_type):
        raise SystemExit(f"invalid or missing config key: {key}")
if config["DESIGN_NAME"] != "tt_um_flowguard_counter":
    raise SystemExit("unexpected DESIGN_NAME")
if config["VERILOG_FILES"] != "dir::src/tt_um_flowguard_counter.v":
    raise SystemExit("VERILOG_FILES must identify the expected design-relative RTL")
sky130 = config.get("pdk::sky130A")
if not isinstance(sky130, dict):
    raise SystemExit("invalid or missing PDK override: pdk::sky130A")
std_cell = sky130.get("scl::sky130_fd_sc_hd")
if not isinstance(std_cell, dict) or not isinstance(std_cell.get("CLOCK_PERIOD"), (int, float)):
    raise SystemExit("invalid or missing standard-cell override: scl::sky130_fd_sc_hd.CLOCK_PERIOD")
if not rtl_path.is_file():
    raise SystemExit(f"missing RTL file: {rtl_path}")
PY

if command -v iverilog >/dev/null; then
  iverilog -g2012 -s tt_um_flowguard_counter -t null "$rtl"
  printf '%s\n' 'Structural validation passed; iverilog compilation passed.'
else
  printf '%s\n' 'Structural validation passed; skipping iverilog compilation (iverilog unavailable).'
fi

if [ "${1:-}" = "--container" ]; then
  exec "$root/scripts/openlane-run.sh"
elif [ "$#" -ne 0 ]; then
  printf '%s\n' "Usage: $0 [--container]" >&2
  exit 2
fi
