import json
import tempfile
import unittest
from pathlib import Path

from src.objective import canonical_objective
from src.parser import append_record, build_record, is_feasible, parse_metrics


FIXTURES = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def test_extracts_common_flat_metrics(self):
        metrics = parse_metrics(FIXTURES / "metrics_success.json")
        self.assertEqual({key: metrics[key] for key in ("area", "WNS", "TNS", "DRC", "wirelength", "status")},
                         {"area": 1234.5, "WNS": 0.12, "TNS": 0, "DRC": 0, "wirelength": 4567, "status": "SUCCESS"})
        self.assertTrue(is_feasible(metrics["status"], metrics["DRC"], metrics["WNS"]))

    def test_extracts_nested_metrics_and_rejects_failure(self):
        metrics = parse_metrics(FIXTURES / "metrics_nested_failure.json")
        self.assertEqual((metrics["area"], metrics["WNS"], metrics["TNS"], metrics["DRC"]), (99.5, -0.03, -1.2, 2))
        self.assertFalse(is_feasible(metrics["status"], metrics["DRC"], metrics["WNS"]))

    def test_appends_immutable_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text(json.dumps({"CLOCK_PERIOD": 10, "FP_CORE_UTIL": 50}))
            record = build_record("one", FIXTURES / "metrics_success.json", 1.5, config=config)
            append_record(record, root)
            self.assertIn("one", (root / "aggregated.csv").read_text())
            with self.assertRaises(FileExistsError):
                append_record(record, root)

    def test_captures_directive_knobs(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text(json.dumps({"GPL_CELL_PADDING": 3, "PL_TARGET_DENSITY_PCT": 72}))
            self.assertEqual(build_record("knobs", FIXTURES / "metrics_complete.json", config=config)["knobs"],
                             {"GPL_CELL_PADDING": 3, "PL_TARGET_DENSITY_PCT": 72})

    def test_appends_runner_failure_stage_column(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "status.json"
            status.write_text(json.dumps({"status": "SUCCESS", "terminal_status": "SUCCESS", "failure_stage": None, "runtime_s": 2.0}))
            record = build_record("stage", FIXTURES / "metrics_success.json", status_path=status)
            append_record(record, root)
            self.assertIn("failure_stage", (root / "aggregated.csv").read_text())

    def test_complete_metrics_preserve_positive_setup_wns_and_signoff(self):
        metrics = parse_metrics(FIXTURES / "metrics_complete.json")
        self.assertEqual(metrics["setup_wns"], 0.25)
        self.assertEqual(metrics["hold_wns"], 0.1)
        self.assertEqual(metrics["routing_completion"], 100)
        self.assertEqual(metrics["lvs_passed"], True)
        self.assertEqual(metrics["missing_metrics"], [])
        self.assertIsNone(metrics["failure_stage"])
        self.assertTrue(is_feasible(metrics["status"], metrics["DRC"], metrics["WNS"], metrics))

    def test_worst_slack_takes_precedence_over_violation_only_wns(self):
        fixture = FIXTURES / "metrics_ws_positive.json"
        metrics = parse_metrics(fixture)
        self.assertEqual(metrics["setup_wns"], 0)
        self.assertEqual(metrics["setup_ws"], 3.9)
        self.assertEqual(metrics["WNS"], 3.9)

    def test_incomplete_success_is_not_feasible(self):
        metrics = parse_metrics(FIXTURES / "metrics_success.json")
        self.assertFalse(is_feasible(metrics["status"], metrics["DRC"], metrics["WNS"], metrics))

    def test_failure_precedence(self):
        self.assertEqual(parse_metrics(FIXTURES / "metrics_timing_fail.json")["failure_stage"], "TIMING_FAIL")
        self.assertEqual(parse_metrics(FIXTURES / "metrics_hold_fail.json")["failure_stage"], "TIMING_FAIL")
        self.assertEqual(parse_metrics(FIXTURES / "metrics_routing_fail.json")["failure_stage"], "ROUTING_FAIL")
        self.assertEqual(parse_metrics(FIXTURES / "metrics_drc_fail.json")["failure_stage"], "DRC_FAIL")
        self.assertEqual(parse_metrics(FIXTURES / "metrics_missing.json")["failure_stage"], "MISSING_METRICS")

    def test_objective_rejects_zero_denominator_and_keeps_raw_components(self):
        metrics = {"setup_wns": 2, "clock_period": 10, "routing_wirelength": 200, "area": 100}
        score = canonical_objective(metrics, {"critical_delay": 10, "wirelength": 100, "cell_area": 50})
        self.assertEqual(score["raw"]["critical_delay"], 8)
        with self.assertRaises(ValueError):
            canonical_objective(metrics, {"critical_delay": 0, "wirelength": 100, "cell_area": 50})


if __name__ == "__main__":
    unittest.main()
