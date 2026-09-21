"""Small, deterministic surrogate models used by FlowGuard acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF


Metric = Literal["cell_area", "wns"]


@dataclass(frozen=True)
class FrozenModelKnobs:
    """Deliberately small, fixed model settings for reproducible experiments."""

    classifier_estimators: int = 50
    calibration_cv: int = 3
    random_state: int = 0


FROZEN_KNOBS = FrozenModelKnobs()


def _features(values: Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or not len(array):
        raise ValueError("features must be a non-empty two-dimensional array")
    if not np.isfinite(array).all():
        raise ValueError("features must be finite")
    return array


class FeasibilityModel:
    """All-attempt feasibility predictor with safe calibration fallbacks."""

    def __init__(self) -> None:
        self.model: CalibratedClassifierCV | RandomForestClassifier | None = None
        self.constant_probability: float | None = None
        self.calibrated = False

    def fit(self, features: Sequence[Sequence[float]], feasible: Sequence[bool]) -> "FeasibilityModel":
        x = _features(features)
        y = np.asarray(feasible, dtype=bool)
        if y.ndim != 1 or len(y) != len(x):
            raise ValueError("feasible must contain one value per feature row")

        classes, counts = np.unique(y, return_counts=True)
        if len(classes) == 1:
            self.constant_probability = float(classes[0])
            self.model = None
            self.calibrated = False
            return self

        base = RandomForestClassifier(
            n_estimators=FROZEN_KNOBS.classifier_estimators,
            random_state=FROZEN_KNOBS.random_state,
            n_jobs=1,
        )
        self.constant_probability = None
        self.calibrated = bool(counts.min() >= FROZEN_KNOBS.calibration_cv)
        if self.calibrated:
            try:
                self.model = CalibratedClassifierCV(base, cv=FROZEN_KNOBS.calibration_cv, method="sigmoid")
                self.model.fit(x, y)
                return self
            except ValueError:
                self.calibrated = False

        self.model = base.fit(x, y)
        return self

    def predict_proba(self, features: Sequence[Sequence[float]]) -> np.ndarray:
        x = _features(features)
        if self.constant_probability is not None:
            return np.full(len(x), self.constant_probability)
        if self.model is None:
            raise RuntimeError("fit must be called before predict_proba")
        probabilities = self.model.predict_proba(x)
        positive = np.flatnonzero(self.model.classes_ == True)
        return probabilities[:, positive[0]] if len(positive) else np.zeros(len(x))


class QualityModel:
    """Independent Gaussian-process QoR surrogates trained on feasible trials."""

    def __init__(self) -> None:
        self.models: dict[Metric, GaussianProcessRegressor | None] = {"cell_area": None, "wns": None}
        self.constants: dict[Metric, float | None] = {"cell_area": None, "wns": None}

    def fit(
        self,
        features: Sequence[Sequence[float]],
        cell_area: Sequence[float],
        wns: Sequence[float],
        feasible: Sequence[bool],
    ) -> "QualityModel":
        x = _features(features)
        mask = np.asarray(feasible, dtype=bool)
        area, slack = np.asarray(cell_area, dtype=float), np.asarray(wns, dtype=float)
        if mask.ndim != 1 or any(len(values) != len(x) for values in (mask, area, slack)):
            raise ValueError("metrics and feasible must contain one value per feature row")
        if not mask.any():
            raise ValueError("at least one feasible observation is required")
        for metric, values in (("cell_area", area), ("wns", slack)):
            y = values[mask]
            if not np.isfinite(y).all():
                raise ValueError(f"{metric} must be finite for feasible observations")
            if len(y) == 1:
                self.constants[metric] = float(y[0])
                self.models[metric] = None
            else:
                kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(1.0, (1e-3, 1e3))
                self.models[metric] = GaussianProcessRegressor(
                    kernel=kernel, alpha=1e-6, normalize_y=True, random_state=FROZEN_KNOBS.random_state
                ).fit(x[mask], y)
                self.constants[metric] = None
        return self

    def predict(self, features: Sequence[Sequence[float]], metric: Metric) -> tuple[np.ndarray, np.ndarray]:
        x = _features(features)
        if metric not in self.models:
            raise ValueError(f"unknown metric: {metric}")
        if self.constants[metric] is not None:
            return np.full(len(x), self.constants[metric]), np.zeros(len(x))
        model = self.models[metric]
        if model is None:
            raise RuntimeError("fit must be called before predict")
        mean, standard_deviation = model.predict(x, return_std=True)
        return np.asarray(mean), np.asarray(standard_deviation)


class FlowGuardModels:
    """Convenience API bundling all-attempt feasibility and feasible-only QoR."""

    def __init__(self) -> None:
        self.feasibility = FeasibilityModel()
        self.quality = QualityModel()

    def fit(
        self,
        features: Sequence[Sequence[float]],
        feasible: Sequence[bool],
        cell_area: Sequence[float],
        wns: Sequence[float],
    ) -> "FlowGuardModels":
        self.feasibility.fit(features, feasible)
        self.quality.fit(features, cell_area, wns, feasible)
        return self
