"""Canonical feasible-only objective calculation."""

from __future__ import annotations

from typing import Any, Mapping


def canonical_objective(metrics: Mapping[str, Any], baselines: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize critical delay, routed wirelength, and area against baselines.

    Raw components are retained so objective records remain auditable. Missing or
    zero baselines are rejected rather than silently producing an invalid score.
    """
    setup_wns = metrics.get("setup_ws", metrics.get("setup_wns", metrics.get("WNS")))
    wirelength = metrics.get("routing_wirelength", metrics.get("wirelength"))
    area = metrics.get("area")
    clock = metrics.get("clock_period", baselines.get("clock_period"))
    raw = {"critical_delay": None if setup_wns is None or clock is None else clock - setup_wns,
           "wirelength": wirelength, "cell_area": area}
    baseline = {"critical_delay": baselines.get("critical_delay", baselines.get("timing")),
                "wirelength": baselines.get("wirelength"), "cell_area": baselines.get("cell_area", baselines.get("area"))}
    missing = [name for name, value in baseline.items() if value is None]
    missing += [name for name, value in raw.items() if value is None]
    if missing:
        raise ValueError(f"missing objective metrics or denominators: {', '.join(missing)}")
    if any(float(value) == 0 for value in baseline.values()):
        raise ValueError("objective denominators must be nonzero")
    normalized = {name: float(raw[name]) / float(baseline[name]) for name in raw}
    score = 0.50 * normalized["critical_delay"] + 0.25 * normalized["wirelength"] + 0.25 * normalized["cell_area"]
    normalized["timing"] = normalized["critical_delay"]
    raw["timing"] = raw["critical_delay"]
    return {"objective": score, "normalized": normalized, "raw": raw,
            "baselines": baseline}


compute_objective = canonical_objective
