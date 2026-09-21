import contextlib
import io
import json
import unittest

from experiments import replay_demo


class ReplayDemoTests(unittest.TestCase):
    def test_committed_evidence_is_read_only_and_traceable(self):
        evidence = replay_demo.load_evidence()
        self.assertRegex(evidence["manifest"]["git_commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(evidence["manifest"]["bundle_commit"], r"^[0-9a-f]{7,40}$")
        self.assertEqual(evidence["decision_record"]["selected_id"], "cb36_002")
        self.assertEqual(evidence["result_checks"]["drc"], 0)
        self.assertTrue(evidence["manifest"]["no_new_runs"])

    def test_output_distinguishes_replay_from_fresh_eda(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(replay_demo.main(), 0)
        text = output.getvalue()
        self.assertIn("REPLAY:", text)
        self.assertIn("physical EDA processes launched: 0", text)
        self.assertIn("FRESH EDA: not run", text)
        self.assertIn("separate characterization run", text)

    def test_frozen_study_summary_matches_reported_results(self):
        aggregates = json.loads(
            (replay_demo.BUNDLE / "03_recomputed_aggregates.json").read_text(encoding="utf-8")
        )
        validation = json.loads(replay_demo.VALIDATION.read_text(encoding="utf-8"))
        methods = aggregates["aggregates_per_method"]
        self.assertEqual(aggregates["n_rows"], 39)
        self.assertEqual(validation["row_checks"]["trace_rows"], 936)
        self.assertEqual(
            [round(methods[name]["mean_failed_eda_runtime_s"], 1) for name in methods],
            [13046.8, 14378.0, 14994.8],
        )
        self.assertTrue(
            all(row["d_best_qor"] == 0 and row["d_best_qor_call"] == 0
                for row in aggregates["paired_flowguard_minus_eionly"])
        )


if __name__ == "__main__":
    unittest.main()
