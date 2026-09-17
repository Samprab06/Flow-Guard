"""Strict, reviewable configuration checks for the pinned LibreLane flow."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


LIBRELANE_VERSION = "3.0.14"

# This is deliberately narrower than LibreLane's complete option surface: the
# experiment may tune placement, timing, and padding, but not the design.
ALLOWLIST = frozenset({
    "CLOCK_PERIOD", "FP_CORE_UTIL", "PL_TARGET_DENSITY_PCT", "GPL_CELL_PADDING",
    "SYNTH_STRATEGY",
    "GRT_ADJUSTMENT", "PL_RESIZER_BUFFER_INPUT_PORTS", "PL_RESIZER_BUFFER_OUTPUT_PORTS",
    "PL_RESIZER_SETUP_SLACK_MARGIN", "PL_RESIZER_HOLD_SLACK_MARGIN",
})
PROTECTED = frozenset({
    "CLOCK_PORT", "CLOCK_NET", "VERILOG_FILES", "SVERILOG_FILES", "DESIGN_NAME",
    "PDK", "PDK_ROOT", "STD_CELL_LIBRARY", "DIE_AREA", "CORE_AREA", "FP_SIZING",
    "TAPCELL_FILES", "CELL_LEF_FILES", "CELL_GDS_FILES", "MACRO_PLACEMENT_CFG",
})

BOUNDS: dict[str, tuple[float, float]] = {
    "CLOCK_PERIOD": (0.1, 1000.0),
    "FP_CORE_UTIL": (1.0, 100.0),
    "PL_TARGET_DENSITY_PCT": (1.0, 100.0),
    "GPL_CELL_PADDING": (0.0, 20.0),
    "GRT_ADJUSTMENT": (0.0, 1.0),
    "PL_RESIZER_SETUP_SLACK_MARGIN": (-100.0, 100.0),
    "PL_RESIZER_HOLD_SLACK_MARGIN": (-100.0, 100.0),
}
BOOLEAN_KEYS = frozenset({"PL_RESIZER_BUFFER_INPUT_PORTS", "PL_RESIZER_BUFFER_OUTPUT_PORTS"})
STRING_KEYS = frozenset({
    "CLOCK_PORT", "CLOCK_NET", "DESIGN_NAME", "PDK", "PDK_ROOT", "STD_CELL_LIBRARY",
    "FP_SIZING", "SYNTH_STRATEGY",
})
SYNTH_STRATEGIES = frozenset(
    {f"AREA {index}" for index in range(4)} |
    {f"DELAY {index}" for index in range(5)}
)
PATH_KEYS = frozenset({"VERILOG_FILES", "SVERILOG_FILES"})


class ConfigError(ValueError):
    """Raised when a candidate attempts to change flow semantics."""


def effective_config_hash(config: Mapping[str, Any]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_config(config: Mapping[str, Any], baseline: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate and return a copy of a LibreLane 3.0.14 candidate config."""
    if not isinstance(config, Mapping):
        raise ConfigError("configuration must be a JSON object")
    for key, value in config.items():
        if not isinstance(key, str):
            raise ConfigError("configuration keys must be strings")
        if key == "CELL_PAD":
            raise ConfigError("CELL_PAD is not a LibreLane 3.0.14 option; use GPL_CELL_PADDING")
        if key not in ALLOWLIST and key not in PROTECTED and not key.startswith("pdk::"):
            raise ConfigError(f"configuration key is not allow-listed: {key}")
        if key.startswith("pdk::") and not isinstance(value, Mapping):
            raise ConfigError(f"{key} must contain a mapping")
        if key in STRING_KEYS and not isinstance(value, str):
            raise ConfigError(f"{key} must be a string")
        if key == "SYNTH_STRATEGY" and value not in SYNTH_STRATEGIES:
            raise ConfigError(f"unsupported SYNTH_STRATEGY: {value}")
        if key in PATH_KEYS and not isinstance(value, (str, list)):
            raise ConfigError(f"{key} must be a path or list of paths")
        if key == "DIE_AREA":
            if not isinstance(value, list) or len(value) != 4 or any(
                isinstance(item, bool) or not isinstance(item, (int, float)) for item in value
            ):
                raise ConfigError("DIE_AREA must contain four numeric coordinates")
        if key in BOUNDS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ConfigError(f"{key} must be numeric")
            low, high = BOUNDS[key]
            if not low <= value <= high:
                raise ConfigError(f"{key} must be between {low} and {high}")
        if key in BOOLEAN_KEYS and not isinstance(value, bool):
            raise ConfigError(f"{key} must be boolean")
    if baseline is not None:
        for key in PROTECTED:
            if key in config and config[key] != baseline.get(key):
                raise ConfigError(f"protected configuration cannot change: {key}")
    return dict(config)


def preflight_config(config: Mapping[str, Any], baseline: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compatibility name for callers performing candidate preflight."""
    return validate_config(config, baseline)
