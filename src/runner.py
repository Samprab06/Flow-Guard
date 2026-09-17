"""Isolated, reproducible LibreLane trial runner."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from .config_schema import effective_config_hash, validate_config


ROOT = Path(__file__).resolve().parents[1]
PINNED_ENV = ROOT / "environment" / "openlane-baseline.env"


def _failure_stage(output: str) -> str | None:
    """Classify a failed LibreLane run from its structured stage/error text."""
    text = output.upper()
    markers = (
        ("SYNTH_FAIL", ("SYNTHESIS FAILED", "YOSYS FAILED", "SYNTH_FAIL")),
        ("PLACEMENT_FAIL", ("GPL-", "GLOBALPLACEMENT", "PLACEMENT FAILED")),
        ("CTS_FAIL", ("CLOCK TREE SYNTHESIS", "CTS_FAIL")),
        ("TIMING_FAIL", ("SETUP VIOLATIONS", "HOLD VIOLATIONS", "TIMING_FAIL")),
        ("ROUTING_FAIL", ("DETAILED ROUTING", "GLOBAL ROUTING", "ROUTING_FAIL")),
        ("DRC_FAIL", ("MAGIC DRC", "KLAYOUT DRC", "DRC_FAIL")),
        ("LVS_FAIL", ("NETGEN LVS", "LVS_FAIL")),
    )
    for stage, needles in markers:
        if any(needle in text for needle in needles):
            return stage
    return "TOOL_CRASH" if text else "INFRASTRUCTURE_FAIL"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_provenance() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            return subprocess.check_output(["git", *args], cwd=ROOT, text=True,
                                           stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
    commit = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain")
    return {"commit": commit, "dirty": dirty is not None and bool(dirty)}


def _source_tree_sha256() -> str | None:
    """Hash the exact tracked source tree used for a trial."""
    try:
        paths = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT, stderr=subprocess.DEVNULL, text=False
        ).split(b"\0")
        digest = hashlib.sha256()
        for raw_path in sorted(path for path in paths if path):
            path = ROOT / os.fsdecode(raw_path)
            if not path.is_file():
                continue
            digest.update(raw_path)
            digest.update(b"\0")
            digest.update(path.read_bytes())
        return digest.hexdigest()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, TypeError):
        return None


def _environment_snapshot(env: Mapping[str, str]) -> dict[str, Any]:
    """Capture reproducibility inputs without archiving arbitrary secrets."""
    snapshot = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
        "librelane_version": _librelane_version(env),
        "librelane_container_image": env.get("LIBRELANE_CONTAINER_IMAGE"),
        "pdk": env.get("PDK"),
        "pdk_root": env.get("PDK_ROOT"),
        "pdk_revision": env.get("SKY130_PDK_REVISION"),
        "std_cell_library": env.get("STD_CELL_LIBRARY"),
    }
    return snapshot


def _environment_sha256(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _librelane_version(env: Mapping[str, str]) -> str | None:
    try:
        return importlib.metadata.version("librelane")
    except importlib.metadata.PackageNotFoundError:
        return env.get("LIBRELANE_VERSION")


def _safe_trial_id(trial_id: str) -> str:
    if not trial_id or any(not (char.isalnum() or char in "_-.") for char in trial_id):
        raise ValueError("trial_id may contain only letters, digits, _, -, and .")
    return trial_id


def _pinned_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Load the repository's checked-in LibreLane pin without shell evaluation."""
    env = dict(os.environ if environ is None else environ)
    for raw_line in PINNED_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("export ") or "=" not in line:
            continue
        key, value = line[7:].split("=", 1)
        value = value.strip().strip('"').strip("'")
        # The baseline only expands these two stable environment expressions.
        value = value.replace("${PDK_ROOT:-$HOME/.ciel}", env.get("PDK_ROOT", str(Path.home() / ".ciel")))
        value = value.replace("$LIBRELANE_CONTAINER_IMAGE", env.get("LIBRELANE_CONTAINER_IMAGE", ""))
        env[key] = value
    return env


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def run_trial(
    trial_id: str,
    config: str | Path,
    timeout: float,
    runs_root: str | Path | None = None,
) -> dict[str, Any]:
    """Run one LibreLane trial and atomically persist its terminal status.

    A completed trial is never overwritten.  The default output location is
    ``<config parent>/runs/trial_<id>``; ``runs_root`` selects another root.
    """
    trial_id = _safe_trial_id(trial_id)
    config_path = Path(config).resolve()
    if not config_path.is_file():
        raise FileNotFoundError(config_path)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    validate_config(config_data)

    default_root = config_path.parent / "runs"
    root = Path(runs_root).resolve() if runs_root else default_root
    run_tag = f"trial_{trial_id}"
    trial_dir = root / run_tag
    produced_dir = default_root / run_tag
    status_path = trial_dir / "status.json"
    if status_path.exists() or trial_dir.exists() or produced_dir.exists():
        raise FileExistsError(f"trial directory already exists: {trial_dir}")
    if not PINNED_ENV.is_file():
        raise FileNotFoundError(PINNED_ENV)

    env = _pinned_environment()
    environment = _environment_snapshot(env)
    executable = ROOT / ".venv" / "openlane" / "bin" / "python"
    command = [
        str(executable if executable.is_file() and os.access(executable, os.X_OK) else Path(sys.executable)),
        "-m", "librelane", "--docker-no-tty", "--dockerized",
        "--pdk-root", env["PDK_ROOT"], "--pdk", env["PDK"],
        "--scl", env["STD_CELL_LIBRARY"], "--run-tag", run_tag,
        str(config_path),
    ]
    started = _utc_now()
    begun = time.monotonic()
    exit_code: int | None = None
    status = "CRASH"
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            command, cwd=config_path.parent, env=env, text=True,
            capture_output=True, timeout=timeout, check=False,
        )
        exit_code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        status = "SUCCESS" if exit_code == 0 else "CRASH"
    except subprocess.TimeoutExpired as error:
        status = "TIMEOUT"
        stdout = error.stdout or ""
        stderr = error.stderr or ""
    runtime_s = time.monotonic() - begun
    combined_output = f"{stdout}\n{stderr}"
    # Exit zero is only a completed tool invocation. Feasibility is assigned by
    # the parser after final timing, routing, DRC, and objective metrics exist.
    terminal_status = (
        "SUCCESS" if status == "SUCCESS"
        else "TIMEOUT" if status == "TIMEOUT"
        else _failure_stage(combined_output)
    )

    # LibreLane creates runs beneath the config; move its isolated tag only
    # when callers selected a different root.
    if root != default_root and produced_dir.exists() and not trial_dir.exists():
        root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced_dir), str(trial_dir))
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / "runner.stdout.log").write_text(stdout, encoding="utf-8")
    (trial_dir / "runner.stderr.log").write_text(stderr, encoding="utf-8")
    result: dict[str, Any] = {
        "trial_id": trial_id,
        "status": status,
        "terminal_status": terminal_status,
        "failure_stage": None if status == "SUCCESS" else terminal_status,
        "runtime_s": runtime_s,
        "started_at": started,
        "finished_at": _utc_now(),
        "exit_code": exit_code,
        "config": str(config_path),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "effective_config_sha256": effective_config_hash(config_data),
        "command": command,
        "metadata": {
            "executable": command[0],
            "sys_executable": sys.executable,
            "python_version": platform.python_version(),
            "librelane_version": _librelane_version(env),
            "librelane_container_image": env.get("LIBRELANE_CONTAINER_IMAGE"),
            "pdk": env.get("PDK"),
            "pdk_root": env.get("PDK_ROOT"),
            "pdk_revision": env.get("SKY130_PDK_REVISION"),
            "std_cell_library": env.get("STD_CELL_LIBRARY"),
            "run_directory": str(trial_dir),
            "host": platform.node(),
            "git": _git_provenance(),
            "source_tree_sha256": _source_tree_sha256(),
            "environment": environment,
            "environment_sha256": _environment_sha256(environment),
        },
    }
    result["failure_metadata"] = None if status == "SUCCESS" else {
        "stage": terminal_status,
        "exit_code": exit_code,
        "timed_out": status == "TIMEOUT",
        "stderr_tail": stderr[-2000:],
        "stdout_tail": stdout[-2000:],
    }
    _atomic_json(status_path, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--timeout", required=True, type=float)
    parser.add_argument("--runs-root")
    args = parser.parse_args(argv)
    try:
        result = run_trial(args.trial_id, args.config, args.timeout, args.runs_root)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
