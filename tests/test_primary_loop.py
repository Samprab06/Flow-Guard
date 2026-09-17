"""Synthetic tests for the frozen primary optimizer comparison (no EDA)."""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.primary_loop import (
    METHODS,
    PROVENANCE_FIELDS,
    compute_pool_hash,
    load_init_ids,
    load_pool,
    main,
    make_driver,
    suggest_with_provenance,
    validate_observed,
)

ROOT = Path(__file__).resolve().parents[1]


def synthetic_pool(n=10):
    """Tiny in-memory pool with varied knobs (no EDA, no disk)."""
    strategies = ["AREA 0", "AREA 1", "AREA 2"]
    pool = []
    for index in range(n):
        pool.append({
            "candidate_id": f"syn_{index:03d}",
            "GPL_CELL_PADDING": index % 2 * 2,
            "PL_TARGET_DENSITY_PCT": (38, 45, 52)[index % 3],
            "GRT_ADJUSTMENT": (0.05, 0.1, 0.15, 0.2)[index % 4],
            "SYNTH_STRATEGY": strategies[index % 3],
        })
    return pool


def synthetic_observed(pool, n_feasible=3, n_infeasible=2):
    """Observed records over the first pool entries (feasible carry QoR)."""
    records = []
    for index in range(n_feasible):
        records.append({"candidate_id": pool[index]["candidate_id"],
                        "feasible": True, "qor": 0.2 + 0.1 * index})
    for index in range(n_feasible, n_feasible + n_infeasible):
        records.append({"candidate_id": pool[index]["candidate_id"],
                        "feasible": False, "qor": None})
    return records


class PrimaryPoolTests(unittest.TestCase):
    def test_real_pool_loads_and_matches_manifest(self):
        pool = load_pool(ROOT / "experiments/pools/pool_15p8_v1.json",
                         ROOT / "experiments/manifests/primary_benchmark_v1.json")
        self.assertEqual(len(pool), 72)

    def test_pool_hash_detects_tampering(self):
        pool = synthetic_pool()
        digest = compute_pool_hash(pool)
        tampered = copy.deepcopy(pool)
        tampered[0]["GRT_ADJUSTMENT"] = 0.99
        self.assertNotEqual(compute_pool_hash(tampered), digest)
        self.assertEqual(compute_pool_hash(copy.deepcopy(pool)), digest)

    def test_init_ids_from_manifest_else_seeded_order(self):
        pool = synthetic_pool()
        ids = load_init_ids(ROOT / "experiments/manifests/primary_init_v1.json",
                            load_pool(ROOT / "experiments/pools/pool_15p8_v1.json"))
        self.assertEqual(len(ids), 8)
        fallback = load_init_ids(ROOT / "does-not-exist.json", pool)
        self.assertEqual(fallback, [row["candidate_id"] for row in pool[:8]])


class PrimaryMethodTests(unittest.TestCase):
    def setUp(self):
        self.pool = synthetic_pool(10)
        self.observed = synthetic_observed(self.pool)

    def test_each_method_returns_legal_unobserved_id(self):
        pool_ids = {row["candidate_id"] for row in self.pool}
        seen = {row["candidate_id"] for row in self.observed}
        for method in METHODS:
            candidate, _ = suggest_with_provenance(
                method, self.observed, self.pool, np.random.default_rng(0))
            self.assertIn(candidate, pool_ids)
            self.assertNotIn(candidate, seen)

    def test_determinism_same_seed_twice(self):
        for method in METHODS:
            first, _ = suggest_with_provenance(
                method, self.observed, self.pool, np.random.default_rng(123))
            second, _ = suggest_with_provenance(
                method, self.observed, self.pool, np.random.default_rng(123))
            self.assertEqual(first, second)

    def test_provenance_fields_complete(self):
        for method in METHODS:
            _, provenance = suggest_with_provenance(
                method, self.observed, self.pool, np.random.default_rng(0),
                call_index=5)
            for field in PROVENANCE_FIELDS:
                self.assertIn(field, provenance)
            self.assertEqual(provenance["method"], method)
            self.assertEqual(provenance["call_index"], 5)
            self.assertEqual(provenance["training_size"], len(self.observed))
            self.assertEqual(len(provenance["data_hash"]), 64)
            for key in ("numpy", "scikit-learn", "optuna", "scipy"):
                self.assertIn(key, provenance["model_versions"])
            self.assertIsInstance(provenance["calibration_active"], bool)
            self.assertEqual(provenance["rank"], 1)
            self.assertIn(provenance["selected_id"],
                          {row["candidate_id"] for row in self.pool})

    def test_model_scores_finite_for_gp_methods(self):
        for method in ("vanilla_bo", "flowguard_raw", "flowguard_calibrated"):
            _, provenance = suggest_with_provenance(
                method, self.observed, self.pool, np.random.default_rng(0))
            for key in ("pred_mean", "pred_var", "p_feas", "ei", "acquisition_score"):
                self.assertTrue(np.isfinite(provenance[key]), (method, key))

    def test_infeasible_no_qor_rule(self):
        bad_infeasible = self.observed + [{"candidate_id": self.pool[5]["candidate_id"],
                                           "feasible": False, "qor": 0.5}]
        bad_feasible = [{"candidate_id": self.pool[0]["candidate_id"],
                         "feasible": True, "qor": None}]
        with self.assertRaises(ValueError):
            validate_observed(bad_infeasible)
        with self.assertRaises(ValueError):
            validate_observed(bad_feasible)
        for method in METHODS:
            with self.assertRaises(ValueError):
                suggest_with_provenance(method, bad_infeasible, self.pool,
                                        np.random.default_rng(0))

    def test_calibration_fallback_when_one_class_small(self):
        pool = synthetic_pool(10)
        few_infeasible = ([{"candidate_id": pool[i]["candidate_id"],
                            "feasible": True, "qor": 0.2 + 0.05 * i} for i in range(5)]
                          + [{"candidate_id": pool[5]["candidate_id"],
                              "feasible": False, "qor": None}])
        _, raw_prov = suggest_with_provenance("flowguard_raw", few_infeasible, pool,
                                              np.random.default_rng(0))
        _, cal_prov = suggest_with_provenance("flowguard_calibrated", few_infeasible,
                                              pool, np.random.default_rng(0))
        self.assertFalse(raw_prov["calibration_active"])
        self.assertFalse(cal_prov["calibration_active"])

    def test_calibration_active_when_each_class_large(self):
        pool = synthetic_pool(12)
        balanced = ([{"candidate_id": pool[i]["candidate_id"],
                      "feasible": True, "qor": 0.2 + 0.05 * i} for i in range(4)]
                    + [{"candidate_id": pool[i]["candidate_id"],
                        "feasible": False, "qor": None} for i in range(4, 8)])
        _, provenance = suggest_with_provenance("flowguard_calibrated", balanced, pool,
                                                np.random.default_rng(0))
        self.assertTrue(provenance["calibration_active"])


def ledger_row(candidate_id, feasible, qor):
    row = {"trial_id": f"t-{candidate_id}", "candidate_id": candidate_id,
           "call_index": 0, "runner_status": "SUCCESS", "parser_status": "PARSED",
           "feasible": feasible, "qor": qor, "finished_at": "2026-09-16T00:00:00Z",
           "experiment": "primary_benchmark_v1"}
    if feasible:
        row["metrics"] = {"setup_ws": 0.5, "hold_ws": 0.11, "area": 15134.5,
                          "wirelength": 27414, "routing_completion": 100,
                          "drc_violations": 0, "lvs_passed": True,
                          "signoff_passed": True, "missing_metrics": []}
    return row


class PrimarySharedTrialsTests(unittest.TestCase):
    def test_shared_trials_merge_with_own_and_exclude_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            pool_file = tmp / "pool.json"
            pool = {"pool_id": "syn", "seed": 0, "size": 10, "candidates": synthetic_pool(10)}
            pool["sha256"] = compute_pool_hash(pool["candidates"])
            pool_file.write_text(json.dumps(pool), encoding="utf-8")
            shared = tmp / "shared.jsonl"
            own = tmp / "own.jsonl"
            shared.write_text("\n".join(json.dumps(ledger_row(f"syn_{i:03d}", True, 0.3))
                                        for i in range(3)) + "\n", encoding="utf-8")
            own.write_text(json.dumps(ledger_row("syn_003", False, None)) + "\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main(["suggest", "--method", "flowguard_raw", "--pool", str(pool_file),
                             "--trials", str(own), "--shared-trials", str(shared),
                             "--call-index", "4"])
            self.assertEqual(code, 0)
            out = json.loads(buf.getvalue())
            self.assertNotIn(out["candidate_id"], {"syn_000", "syn_001", "syn_002", "syn_003"})
            self.assertEqual(out["provenance"]["training_size"], 4)
            self.assertEqual(out["provenance"]["call_index"], 4)


if __name__ == "__main__":
    unittest.main()
