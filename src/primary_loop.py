"""Frozen primary optimizer comparison drivers (primary_benchmark_v1).

Five method drivers share one interface::

    suggest(observed_records, pool, rng) -> candidate_id

Methods: ``random`` / ``optuna_tpe`` / ``vanilla_bo`` / ``flowguard_raw`` /
``flowguard_calibrated``.

Conventions (frozen):
  * Minimization on QoR (lower is better). QoR is min-max normalized to
    roughly [0, 1] by experiments/objective_qor_v1.json.
  * Feasible-only QoR: infeasible records carry ``qor=None`` (enforced).
  * ``vanilla_bo`` trains its GP on all trials with the predeclared frozen
    infeasible penalty :data:`INFEASIBLE_PENALTY`.
  * ``flowguard_raw`` / ``flowguard_calibrated`` train the QoR GP on
    feasible trials only and multiply EI by P(feasible) from an RF trained
    on all trials. No hard risk threshold (per manifest acquisition).
  * ``flowguard_raw`` never calibrates (``calibration_active=False``);
    ``flowguard_calibrated`` calibrates only when each class has >= 3
    samples (via :class:`src.models.FeasibilityModel`).
  * Deterministic per-method seeds (:data:`METHOD_SEEDS`); ties break to
    the first candidate in pool order.

Third-party imports are limited to numpy/sklearn/optuna/scipy plus local
``src.*`` modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import optuna
import scipy
import sklearn
from scipy.stats import norm
from sklearn.ensemble import RandomForestClassifier
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF
from sklearn.preprocessing import StandardScaler

from .models import FROZEN_KNOBS, FeasibilityModel

optuna.logging.set_verbosity(optuna.logging.WARNING)

METHODS = ("random", "optuna_tpe", "vanilla_bo", "flowguard_raw", "flowguard_calibrated")

METHOD_SEEDS = {
    "random": 1337,
    "optuna_tpe": 1338,
    "vanilla_bo": 1339,
    "flowguard_raw": 1340,
    "flowguard_calibrated": 1341,
}

#: Predeclared frozen infeasible penalty for vanilla BO / TPE ranking.
#: QoR is min-max normalized to [0, 1], so 1.0 is the worst attainable
#: feasible score; infeasible trials are strictly worse than any feasible one.
INFEASIBLE_PENALTY = 1.0

#: Minimum per-class count required to activate RF calibration.
MIN_CLASS_FOR_CALIBRATION = 3

MODEL_VERSIONS = {
    "numpy": np.__version__,
    "scikit-learn": sklearn.__version__,
    "optuna": optuna.__version__,
    "scipy": scipy.__version__,
}

SYNTH_INDEX = {"AREA 0": 0.0, "AREA 1": 1.0, "AREA 2": 2.0, "AREA 3": 3.0}

PROVENANCE_FIELDS = (
    "method", "seed", "call_index", "training_candidate_ids", "training_size",
    "data_hash", "model_versions", "calibration_active", "calibration_detail",
    "pred_mean", "pred_var", "p_feas", "ei", "acquisition_score",
    "rank", "n_candidates_scored", "selected_id",
)


# ---------------------------------------------------------------------------
# Pool / observed-record helpers
# ---------------------------------------------------------------------------

def compute_pool_hash(candidates: Sequence[Mapping[str, Any]]) -> str:
    """sha256 of the compact canonical JSON of the candidates array."""
    payload = json.dumps(list(candidates), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_pool(pool_path: str | Path, manifest_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load pool candidates, verifying size and sha256 (plus manifest match)."""
    pool = json.loads(Path(pool_path).read_text(encoding="utf-8"))
    candidates = list(pool["candidates"])
    if pool.get("size") is not None and len(candidates) != pool["size"]:
        raise ValueError(f"pool size mismatch: {len(candidates)} != {pool['size']}")
    if compute_pool_hash(candidates) != pool.get("sha256"):
        raise ValueError("pool sha256 mismatch: candidates do not match recorded hash")
    if manifest_path is not None:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        ref = manifest["candidate_pool"]
        if ref.get("sha256") != pool.get("sha256") or ref.get("size") != len(candidates):
            raise ValueError("pool does not match manifest candidate_pool reference")
    return candidates


def load_init_ids(init_path: str | Path, pool: Sequence[Mapping[str, Any]]) -> list[str]:
    """Shared init IDs from the init manifest, else first 8 pool IDs in order."""
    pool_ids = [str(row["candidate_id"]) for row in pool]
    if init_path is not None and Path(init_path).exists():
        init = json.loads(Path(init_path).read_text(encoding="utf-8"))
        ids = [str(value) for value in init["shared_candidate_ids"]]
        unknown = [value for value in ids if value not in pool_ids]
        if unknown:
            raise ValueError(f"init IDs not in pool: {unknown}")
        return ids
    return pool_ids[:8]


def validate_observed(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Enforce the infeasible-no-QoR rule and return normalized records."""
    cleaned: list[dict[str, Any]] = []
    for record in records:
        candidate_id = str(record["candidate_id"])
        feasible = bool(record["feasible"])
        qor = record.get("qor")
        if feasible:
            if qor is None or not np.isfinite(float(qor)):
                raise ValueError(f"feasible record {candidate_id} must carry a finite QoR")
            cleaned.append({"candidate_id": candidate_id, "feasible": True, "qor": float(qor)})
        else:
            if qor is not None:
                raise ValueError(f"infeasible record {candidate_id} must not carry a QoR")
            cleaned.append({"candidate_id": candidate_id, "feasible": False, "qor": None})
    return cleaned


def compute_data_hash(records: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(
        [{"candidate_id": r["candidate_id"], "feasible": r["feasible"], "qor": r["qor"]}
         for r in sorted(records, key=lambda r: r["candidate_id"])],
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_qor(cell_area: float, critical_delay_ns: float, wirelength_um: float,
                baselines: Mapping[str, Any]) -> float:
    """Frozen qor_v1 formula: 0.5*crit + 0.3*wl + 0.2*area (min-max norm)."""
    lo_c, hi_c = float(baselines["min_crit_ns"]), float(baselines["max_crit_ns"])
    lo_w, hi_w = float(baselines["min_wl_um"]), float(baselines["max_wl_um"])
    lo_a, hi_a = float(baselines["min_area_um2"]), float(baselines["max_area_um2"])
    if hi_c == lo_c or hi_w == lo_w or hi_a == lo_a:
        raise ValueError("objective denominators must be nonzero")
    for name, value in (("cell_area", cell_area), ("critical_delay", critical_delay_ns),
                        ("wirelength", wirelength_um)):
        if not np.isfinite(float(value)):
            raise ValueError(f"{name} must be finite")
    return (0.5 * (float(critical_delay_ns) - lo_c) / (hi_c - lo_c)
            + 0.3 * (float(wirelength_um) - lo_w) / (hi_w - lo_w)
            + 0.2 * (float(cell_area) - lo_a) / (hi_a - lo_a))


def build_observed_from_trials(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Map ledger trial rows to observed records (candidate_id/feasible/qor)."""
    return validate_observed([
        {"candidate_id": row["candidate_id"], "feasible": row["feasible"], "qor": row.get("qor")}
        for row in rows
    ])


# ---------------------------------------------------------------------------
# Features / surrogate helpers
# ---------------------------------------------------------------------------

def encode_row(candidate: Mapping[str, Any]) -> list[float]:
    try:
        return [float(candidate["GPL_CELL_PADDING"]),
                float(candidate["PL_TARGET_DENSITY_PCT"]),
                float(candidate["GRT_ADJUSTMENT"]),
                float(SYNTH_INDEX[str(candidate["SYNTH_STRATEGY"])])]
    except KeyError as error:
        raise ValueError(f"candidate missing knob: {error}") from error


def encode_matrix(candidates: Sequence[Mapping[str, Any]]) -> np.ndarray:
    return np.asarray([encode_row(row) for row in candidates], dtype=float)


def scale_features(pool: Sequence[Mapping[str, Any]],
                   rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    """Standardize with pool statistics (frozen pool => deterministic)."""
    scaler = StandardScaler().fit(encode_matrix(pool))
    return scaler.transform(encode_matrix(pool)), scaler.transform(encode_matrix(rows))


class _ConstantGP:
    """Single-point / degenerate GP fallback: zero variance, mean=value."""

    def __init__(self, value: float) -> None:
        self.value = float(value)

    def predict(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        mean = np.full(len(x), self.value)
        return mean, np.zeros(len(x))


def fit_qor_gp(x_train: np.ndarray, y_train: np.ndarray, seed: int):
    values = np.asarray(y_train, dtype=float)
    if len(values) < 2 or bool((values == values[0]).all()):
        return _ConstantGP(float(values[0]))
    kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(1.0, (1e-3, 1e3))
    return GaussianProcessRegressor(kernel=kernel, alpha=1e-6,
                                    normalize_y=True, random_state=seed).fit(x_train, values)


def gp_predict(model, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if isinstance(model, _ConstantGP):
        return model.predict(x)
    mean, std = model.predict(x, return_std=True)
    std = np.maximum(np.asarray(std, dtype=float), 0.0)
    return np.asarray(mean, dtype=float), std ** 2


def expected_improvement(mean: np.ndarray, var: np.ndarray, best: float) -> np.ndarray:
    std = np.sqrt(np.maximum(np.asarray(var, dtype=float), 0.0))
    improvement = np.asarray(best, dtype=float) - np.asarray(mean, dtype=float)
    z = np.divide(improvement, std, out=np.zeros_like(improvement), where=std > 0)
    ei = improvement * norm.cdf(z) + std * norm.pdf(z)
    ei = np.where(std > 0, np.maximum(ei, 0.0), np.maximum(improvement, 0.0))
    return np.asarray(ei, dtype=float)


def _fit_raw_rf(x_train: np.ndarray, y_train: np.ndarray, seed: int):
    """Uncalibrated all-trials RF; constant fallback for single-class data."""
    classes, counts = np.unique(np.asarray(y_train, dtype=bool), return_counts=True)
    if len(classes) == 1:
        return float(classes[0]), "single-class-constant"
    model = RandomForestClassifier(n_estimators=FROZEN_KNOBS.classifier_estimators,
                                   random_state=seed, n_jobs=1).fit(x_train, y_train)
    return model, "uncalibrated-rf"


def _raw_predict_proba(model, x: np.ndarray) -> np.ndarray:
    if isinstance(model, float):
        return np.full(len(x), model)
    proba = model.predict_proba(x)
    positive = np.flatnonzero(np.asarray(model.classes_) == True)
    return proba[:, positive[0]] if len(positive) else np.zeros(len(x))


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------

@dataclass
class SuggestionContext:
    observed: list[dict[str, Any]]
    pool: list[dict[str, Any]]
    unobserved: list[dict[str, Any]]
    x_pool_scaled: np.ndarray
    x_unobs_scaled: np.ndarray


@dataclass
class MethodDriver:
    method: str
    seed: int = 0
    call_index: int = 0
    last_provenance: dict[str, Any] | None = field(default=None, init=False)

    def suggest(self, observed_records: Sequence[Mapping[str, Any]],
                pool: Sequence[Mapping[str, Any]], rng: np.random.Generator) -> str:
        raise NotImplementedError

    # -- shared plumbing ----------------------------------------------------
    def _context(self, observed_records, pool) -> SuggestionContext:
        if self.method not in METHODS:
            raise ValueError(f"unknown method: {self.method}")
        pool = list(pool)
        ids = [str(row["candidate_id"]) for row in pool]
        if len(set(ids)) != len(ids):
            raise ValueError("pool candidate_ids must be unique")
        observed = validate_observed(observed_records)
        seen = {row["candidate_id"] for row in observed}
        unknown = seen - set(ids)
        if unknown:
            raise ValueError(f"observed IDs not in pool: {sorted(unknown)}")
        if len(observed) != len(seen):
            raise ValueError("observed records contain duplicate candidate_ids")
        unobserved = [row for row in pool if str(row["candidate_id"]) not in seen]
        if not unobserved:
            raise ValueError("no unobserved candidates remain")
        x_pool, x_unobs = scale_features(pool, unobserved)
        return SuggestionContext(observed, pool, unobserved, x_pool, x_unobs)

    def _base_provenance(self, ctx: SuggestionContext, calibration_active: bool,
                         calibration_detail: str) -> dict[str, Any]:
        return {
            "method": self.method,
            "seed": self.seed,
            "call_index": self.call_index,
            "training_candidate_ids": [row["candidate_id"] for row in ctx.observed],
            "training_size": len(ctx.observed),
            "data_hash": compute_data_hash(ctx.observed),
            "model_versions": dict(MODEL_VERSIONS),
            "calibration_active": bool(calibration_active),
            "calibration_detail": calibration_detail,
            "pred_mean": None, "pred_var": None, "p_feas": None,
            "ei": None, "acquisition_score": None,
            "rank": 1, "n_candidates_scored": len(ctx.unobserved),
            "selected_id": "",
        }

    @staticmethod
    def _finish(prov: dict[str, Any], selected_position: int,
                scores: np.ndarray | Sequence[float]) -> str:
        scores = np.asarray(scores, dtype=float)
        prov["rank"] = int(1 + np.sum(scores > scores[selected_position]))
        return prov["selected_id"]


class RandomDriver(MethodDriver):
    def suggest(self, observed_records, pool, rng) -> str:
        ctx = self._context(observed_records, pool)
        prov = self._base_provenance(ctx, False, "random: no model")
        position = int(rng.integers(0, len(ctx.unobserved)))
        prov["selected_id"] = str(ctx.unobserved[position]["candidate_id"])
        self.last_provenance = prov
        return self._finish(prov, position, np.zeros(len(ctx.unobserved)))


class OptunaTPEDriver(MethodDriver):
    _DIST = {
        "GPL_CELL_PADDING": None, "PL_TARGET_DENSITY_PCT": None,
        "GRT_ADJUSTMENT": None, "SYNTH_STRATEGY": None,
    }

    def _distributions(self):
        return {
            "GPL_CELL_PADDING": optuna.distributions.CategoricalDistribution([0, 2]),
            "PL_TARGET_DENSITY_PCT": optuna.distributions.CategoricalDistribution([38, 45, 52]),
            "GRT_ADJUSTMENT": optuna.distributions.CategoricalDistribution([0.05, 0.1, 0.15, 0.2]),
            "SYNTH_STRATEGY": optuna.distributions.CategoricalDistribution(
                ["AREA 0", "AREA 1", "AREA 2"]),
        }

    def suggest(self, observed_records, pool, rng) -> str:
        ctx = self._context(observed_records, pool)
        prov = self._base_provenance(ctx, False, "optuna-tpe: no calibration")
        by_id = {str(row["candidate_id"]): row for row in ctx.pool}
        distributions = self._distributions()
        study = optuna.create_study(direction="minimize",
                                    sampler=optuna.samplers.TPESampler(seed=self.seed))
        for record in ctx.observed:
            candidate = by_id[record["candidate_id"]]
            params = {"GPL_CELL_PADDING": int(candidate["GPL_CELL_PADDING"]),
                      "PL_TARGET_DENSITY_PCT": int(candidate["PL_TARGET_DENSITY_PCT"]),
                      "GRT_ADJUSTMENT": float(candidate["GRT_ADJUSTMENT"]),
                      "SYNTH_STRATEGY": str(candidate["SYNTH_STRATEGY"])}
            trial = study.ask(distributions)
            value = record["qor"] if record["feasible"] else INFEASIBLE_PENALTY
            study.tell(trial, float(value))
        asked = study.ask(distributions)
        params = asked.params
        exact = [row for row in ctx.unobserved
                 if int(row["GPL_CELL_PADDING"]) == params["GPL_CELL_PADDING"]
                 and int(row["PL_TARGET_DENSITY_PCT"]) == params["PL_TARGET_DENSITY_PCT"]
                 and float(row["GRT_ADJUSTMENT"]) == params["GRT_ADJUSTMENT"]
                 and str(row["SYNTH_STRATEGY"]) == params["SYNTH_STRATEGY"]]
        if exact:
            chosen = exact[0]
        else:
            target = np.array([[float(params["GPL_CELL_PADDING"]),
                                float(params["PL_TARGET_DENSITY_PCT"]),
                                float(params["GRT_ADJUSTMENT"]),
                                float(SYNTH_INDEX[str(params["SYNTH_STRATEGY"])])]])
            scaler = StandardScaler().fit(encode_matrix(ctx.pool))
            target_s = scaler.transform(target)[0]
            distances = np.linalg.norm(ctx.x_unobs_scaled - target_s, axis=1)
            chosen = ctx.unobserved[int(np.argmin(distances))]
        position = ctx.unobserved.index(chosen)
        prov["selected_id"] = str(chosen["candidate_id"])
        self.last_provenance = prov
        return self._finish(prov, position, np.zeros(len(ctx.unobserved)))


class VanillaBODriver(MethodDriver):
    def suggest(self, observed_records, pool, rng) -> str:
        ctx = self._context(observed_records, pool)
        prov = self._base_provenance(ctx, False, "vanilla-bo: no feasibility model")
        if not ctx.observed:
            prov["calibration_detail"] = "vanilla-bo: cold-start (no observations)"
            prov["selected_id"] = str(ctx.unobserved[0]["candidate_id"])
            self.last_provenance = prov
            return self._finish(prov, 0, np.zeros(len(ctx.unobserved)))
        x_train = np.array([ctx.x_pool_scaled[
            [str(row["candidate_id"]) for row in ctx.pool].index(row["candidate_id"])]
            for row in ctx.observed])
        y_train = np.array([row["qor"] if row["feasible"] else INFEASIBLE_PENALTY
                            for row in ctx.observed])
        best = float(np.min(y_train))
        model = fit_qor_gp(x_train, y_train, self.seed)
        mean, var = gp_predict(model, ctx.x_unobs_scaled)
        ei = expected_improvement(mean, var, best)
        position = int(np.argmax(ei))
        prov.update({"pred_mean": float(mean[position]), "pred_var": float(var[position]),
                     "p_feas": 1.0, "ei": float(ei[position]),
                     "acquisition_score": float(ei[position]),
                     "selected_id": str(ctx.unobserved[position]["candidate_id"])})
        self.last_provenance = prov
        return self._finish(prov, position, ei)


class _FlowGuardBaseDriver(MethodDriver):
    calibrated: bool = False

    def suggest(self, observed_records, pool, rng) -> str:
        ctx = self._context(observed_records, pool)
        if not ctx.observed:
            prov = self._base_provenance(ctx, False, "flowguard: cold-start (no observations)")
            prov["selected_id"] = str(ctx.unobserved[0]["candidate_id"])
            self.last_provenance = prov
            return self._finish(prov, 0, np.zeros(len(ctx.unobserved)))
        pool_ids = [str(row["candidate_id"]) for row in ctx.pool]
        feasible = [row for row in ctx.observed if row["feasible"]]
        x_all = np.array([ctx.x_pool_scaled[pool_ids.index(row["candidate_id"])]
                          for row in ctx.observed])
        y_all = np.array([row["feasible"] for row in ctx.observed])
        classes, counts = np.unique(y_all, return_counts=True)

        if self.calibrated:
            feas_model = FeasibilityModel().fit(x_all.tolist(), y_all.tolist())
            p_feas = np.asarray(feas_model.predict_proba(ctx.x_unobs_scaled.tolist()),
                                dtype=float)
            calibration_active = bool(feas_model.calibrated)
            detail = ("calibrated-rf(cv=3)" if calibration_active
                      else f"rf-fallback: class_counts={sorted(counts.tolist())}")
        else:
            raw, detail = _fit_raw_rf(x_all, y_all, self.seed)
            p_feas = _raw_predict_proba(raw, ctx.x_unobs_scaled)
            calibration_active = False
        prov = self._base_provenance(ctx, calibration_active, detail)

        if not feasible:
            position = int(np.argmax(p_feas))
            prov.update({"p_feas": float(p_feas[position]),
                         "acquisition_score": float(p_feas[position]),
                         "selected_id": str(ctx.unobserved[position]["candidate_id"])})
            self.last_provenance = prov
            return self._finish(prov, position, p_feas)

        best = float(min(row["qor"] for row in feasible))
        x_feas = np.array([ctx.x_pool_scaled[pool_ids.index(row["candidate_id"])]
                           for row in feasible])
        y_feas = np.array([row["qor"] for row in feasible])
        model = fit_qor_gp(x_feas, y_feas, self.seed)
        mean, var = gp_predict(model, ctx.x_unobs_scaled)
        ei = expected_improvement(mean, var, best)
        scores = np.maximum(ei, 0.0) * np.asarray(p_feas, dtype=float)
        position = int(np.argmax(scores))
        prov.update({"pred_mean": float(mean[position]), "pred_var": float(var[position]),
                     "p_feas": float(p_feas[position]), "ei": float(ei[position]),
                     "acquisition_score": float(scores[position]),
                     "selected_id": str(ctx.unobserved[position]["candidate_id"])})
        self.last_provenance = prov
        return self._finish(prov, position, scores)


class FlowGuardRawDriver(_FlowGuardBaseDriver):
    calibrated = False


class FlowGuardCalibratedDriver(_FlowGuardBaseDriver):
    calibrated = True


_DRIVERS = {
    "random": RandomDriver,
    "optuna_tpe": OptunaTPEDriver,
    "vanilla_bo": VanillaBODriver,
    "flowguard_raw": FlowGuardRawDriver,
    "flowguard_calibrated": FlowGuardCalibratedDriver,
}


def make_driver(method: str, call_index: int = 0) -> MethodDriver:
    """Build the frozen driver for *method* with its deterministic seed."""
    if method not in _DRIVERS:
        raise ValueError(f"unknown method: {method} (expected one of {METHODS})")
    return _DRIVERS[method](method=method, seed=METHOD_SEEDS[method], call_index=call_index)


def suggest_with_provenance(method: str, observed_records: Sequence[Mapping[str, Any]],
                            pool: Sequence[Mapping[str, Any]],
                            rng: np.random.Generator,
                            call_index: int = 0) -> tuple[str, dict[str, Any]]:
    """One-shot suggest returning (candidate_id, provenance record)."""
    driver = make_driver(method, call_index=call_index)
    candidate_id = driver.suggest(observed_records, pool, rng)
    assert driver.last_provenance is not None
    missing = [key for key in PROVENANCE_FIELDS if key not in driver.last_provenance]
    if missing:
        raise RuntimeError(f"incomplete provenance: {missing}")
    return candidate_id, driver.last_provenance


# ---------------------------------------------------------------------------
# CLI (used by scripts/launch_primary_v1.sh; ML runtime only)
# ---------------------------------------------------------------------------

def _cmd_suggest(args: argparse.Namespace) -> int:
    pool = load_pool(args.pool, args.manifest)
    if args.trials:
        rows = [json.loads(line) for line in Path(args.trials).read_text(encoding="utf-8").splitlines()
                if line.strip()]
        observed = build_observed_from_trials(rows)
    elif args.observed:
        observed = validate_observed(json.loads(args.observed))
    else:
        observed = []
    if args.shared_trials:
        shared_rows = [json.loads(line) for line in Path(args.shared_trials).read_text(encoding="utf-8").splitlines()
                       if line.strip()]
        observed = build_observed_from_trials(shared_rows) + observed
    seed = args.seed if args.seed is not None else (METHOD_SEEDS[args.method] + args.call_index)
    rng = np.random.default_rng(seed)
    candidate_id, provenance = suggest_with_provenance(
        args.method, observed, pool, rng, call_index=args.call_index)
    print(json.dumps({"candidate_id": candidate_id, "provenance": provenance}, sort_keys=True))
    return 0


def _cmd_qor(args: argparse.Namespace) -> int:
    objective = json.loads(Path(args.objective).read_text(encoding="utf-8"))
    value = compute_qor(args.area, args.critical_delay, args.wirelength, objective["baselines"])
    print(json.dumps({"qor": value}, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    suggest = sub.add_parser("suggest", help="suggest next candidate_id")
    suggest.add_argument("--method", required=True, choices=list(METHODS))
    suggest.add_argument("--pool", required=True)
    suggest.add_argument("--manifest")
    suggest.add_argument("--trials")
    suggest.add_argument("--shared-trials")
    suggest.add_argument("--observed")
    suggest.add_argument("--call-index", type=int, default=0)
    suggest.add_argument("--seed", type=int, default=None)
    qor = sub.add_parser("qor", help="compute frozen qor_v1 from metrics")
    qor.add_argument("--objective", required=True)
    qor.add_argument("--area", type=float, required=True)
    qor.add_argument("--critical-delay", type=float, required=True)
    qor.add_argument("--wirelength", type=float, required=True)
    args = parser.parse_args(argv)
    if args.command == "suggest":
        return _cmd_suggest(args)
    return _cmd_qor(args)


if __name__ == "__main__":
    raise SystemExit(main())
