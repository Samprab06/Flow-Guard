#!/usr/bin/env bash
# Install the pinned LibreLane launcher, container, and compatible Sky130 PDK.
set -euo pipefail

root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
# shellcheck source=environment/openlane-baseline.env
source "$root/environment/openlane-baseline.env"

if [ "$#" -ne 0 ]; then
  printf '%s\n' "Usage: $0" >&2
  exit 2
fi

for command in bash docker python3.12; do
  command -v "$command" >/dev/null || {
    printf '%s\n' "Required prerequisite is unavailable: $command" >&2
    exit 1
  }
done
python3.12 -m venv --help >/dev/null 2>&1 || {
  printf '%s\n' 'Python 3.12 venv support is required (install python3.12-venv).' >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  printf '%s\n' 'Docker is installed but unavailable to this user. Log out and back in after joining the docker group.' >&2
  exit 1
}

venv="$root/.venv/openlane"
if [ ! -x "$venv/bin/python" ]; then
  mkdir -p "$(dirname "$venv")"
  python3.12 -m venv "$venv"
fi
venv_python_version="$("$venv/bin/python" -c 'import platform; print(platform.python_version())')"
case "$venv_python_version" in
  3.12.*) ;;
  *)
    printf '%s\n' "Existing environment uses Python $venv_python_version; remove $venv and rerun." >&2
    exit 1
    ;;
esac

"$venv/bin/python" -m pip install --require-hashes \
  --requirement "$root/environment/librelane.lock"

"$venv/bin/python" - "$LIBRELANE_VERSION" "$SKY130_PDK_REVISION" <<'PY'
import importlib.metadata
import importlib.resources
import sys

import yaml

expected_version, expected_pdk = sys.argv[1:]
actual_version = importlib.metadata.version("librelane")
if actual_version != expected_version:
    raise SystemExit(f"LibreLane version mismatch: {actual_version} != {expected_version}")
with importlib.resources.files("librelane").joinpath("pdk_hashes.yaml").open() as stream:
    actual_pdk = yaml.safe_load(stream)["sky130"]
if actual_pdk != expected_pdk:
    raise SystemExit(f"Sky130 revision mismatch: {actual_pdk} != {expected_pdk}")
PY

mkdir -p "$PDK_ROOT"
"$venv/bin/python" -m librelane \
  --docker-no-tty --dockerized --pdk-root "$PDK_ROOT" --smoke-test

printf '%s\n' "LibreLane $LIBRELANE_VERSION and Sky130 revision $SKY130_PDK_REVISION are ready."
docker image inspect --format '{{join .RepoDigests "\n"}}' "$LIBRELANE_CONTAINER_IMAGE"
