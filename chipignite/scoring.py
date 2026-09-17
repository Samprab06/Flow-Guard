"""Transparent GO/HOLD/NO-GO scoring for corpus migration candidates."""
from __future__ import annotations

from typing import Any


def score_candidate(metadata: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "repository": bool(metadata.get("repository")),
        "commit": bool(metadata.get("commit")),
        "license": bool(metadata.get("license")),
        "artifacts": bool(metadata.get("artifacts")),
    }
    score = sum(checks.values())
    return {"score": score, "max_score": len(checks), "checks": checks, "decision": decision(score, checks)}


def decision(score: int, checks: dict[str, bool] | None = None) -> str:
    checks = checks or {}
    if not checks.get("repository", score >= 4) or not checks.get("commit", score >= 4):
        return "NO-GO"
    if checks.get("license") is False:
        return "HOLD"
    if score >= 4:
        return "GO"
    return "HOLD"
