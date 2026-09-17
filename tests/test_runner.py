import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.runner import run_trial


class RunnerTests(unittest.TestCase):
    def test_records_success_in_isolated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text("{}")
            completed = type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
            with patch("src.runner.subprocess.run", return_value=completed):
                result = run_trial("abc-1", config, 2, root / "runs")
            status = json.loads((root / "runs" / "trial_abc-1" / "status.json").read_text())
            self.assertEqual(result["status"], "SUCCESS")
            self.assertEqual(status["trial_id"], "abc-1")
            self.assertTrue((root / "runs" / "trial_abc-1" / "runner.stdout.log").exists())
            self.assertIn("source_tree_sha256", result["metadata"])
            self.assertRegex(result["metadata"]["environment_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(result["config_sha256"], hashlib.sha256(b"{}").hexdigest())

    def test_records_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text("{}")
            with patch("src.runner.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(["x"], 1)):
                result = run_trial("timeout", config, 1, root / "runs")
            self.assertEqual(result["status"], "TIMEOUT")
            self.assertEqual(result["terminal_status"], "TIMEOUT")
            self.assertEqual(result["failure_stage"], "TIMEOUT")

    def test_records_nonzero_exit_as_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text("{}")
            completed = type("Completed", (), {"returncode": 7, "stdout": "", "stderr": "failure"})()
            with patch("src.runner.subprocess.run", return_value=completed):
                result = run_trial("crash", config, 1, root / "runs")
            self.assertEqual(result["status"], "CRASH")
            self.assertEqual(result["exit_code"], 7)
            self.assertIn("sys_executable", result["metadata"])
            self.assertIn("python_version", result["metadata"])
            self.assertIn("pdk_root", result["metadata"])
            self.assertIn("git", result["metadata"])
            self.assertEqual(result["failure_metadata"]["exit_code"], 7)

    def test_classifies_librelane_placement_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text("{}")
            completed = type("Completed", (), {
                "returncode": 2,
                "stdout": "[GPL-0301] Utilization exceeds 100%",
                "stderr": "",
            })()
            with patch("src.runner.subprocess.run", return_value=completed):
                result = run_trial("placement", config, 1, root / "runs")
            self.assertEqual(result["status"], "CRASH")
            self.assertEqual(result["terminal_status"], "PLACEMENT_FAIL")
            self.assertEqual(result["failure_stage"], "PLACEMENT_FAIL")

    def test_completed_trial_is_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config.json"
            config.write_text("{}")
            completed = type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
            with patch("src.runner.subprocess.run", return_value=completed):
                run_trial("immutable", config, 2, root / "runs")
                with self.assertRaises(FileExistsError):
                    run_trial("immutable", config, 2, root / "runs")


if __name__ == "__main__":
    unittest.main()
