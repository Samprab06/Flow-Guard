"""Risk-aware, deterministic acquisition for FlowGuard."""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, pi, sqrt
from typing import Sequence

import numpy as np

from models.models import FlowGuardModels, Metric, _features


MIN_FEASIBILITY_PROBABILITY = 0.35

FROZEN_SEARCH_SPACE = {
    "PL_TARGET_DENSITY": (0.40, 0.70),
    "CELL_PAD": (1, 4),
    "SYNTH_STRATEGY": ("AREA 0", "AREA 1", "AREA 2", "AREA 3"),
    "FP_CORE_UTIL": (35, 60),
}


@dataclass(frozen=True)
class AcquisitionResult:
    index: int
    score: float
    scores: np.ndarray


def _normal_cdf(values: np.ndarray) -> np.ndarray:
    return np.asarray([0.5 * (1.0 + erf(float(value) / sqrt(2.0))) for value in values])


def constrained_expected_improvement(
    candidates: Sequence[Sequence[float]],
    models: FlowGuardModels,
    best_cell_area: float,
    *,
    risk_threshold: float = MIN_FEASIBILITY_PROBABILITY,
) -> np.ndarray:
    """Return area EI times feasibility probability, abstaining below risk threshold."""
    x = _features(candidates)
    if not 0.0 <= risk_threshold <= 1.0 or not np.isfinite(best_cell_area):
        raise ValueError("risk_threshold and best_cell_area must be finite probabilities/values")
    mean, standard_deviation = models.quality.predict(x, "cell_area")
    probability = models.feasibility.predict_proba(x)
    safe_std = np.maximum(standard_deviation, 0.0)
    improvement = best_cell_area - mean
    z = np.divide(improvement, safe_std, out=np.zeros_like(improvement), where=safe_std > 0)
    ei = improvement * _normal_cdf(z) + safe_std * np.exp(-0.5 * z * z) / sqrt(2.0 * pi)
    ei[safe_std == 0] = np.maximum(improvement[safe_std == 0], 0.0)
    scores = np.maximum(ei, 0.0) * probability
    scores[probability < risk_threshold] = 0.0
    return scores


def select_candidate(
    candidates: Sequence[Sequence[float]],
    models: FlowGuardModels,
    best_cell_area: float,
    *,
    risk_threshold: float = MIN_FEASIBILITY_PROBABILITY,
) -> AcquisitionResult:
    """Select the first maximum-scoring candidate for deterministic tie breaking."""
    scores = constrained_expected_improvement(candidates, models, best_cell_area, risk_threshold=risk_threshold)
    index = int(np.argmax(scores))
    return AcquisitionResult(index=index, score=float(scores[index]), scores=scores)
