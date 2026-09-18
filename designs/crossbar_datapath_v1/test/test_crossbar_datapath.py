"""Self-contained deterministic RTL regression for crossbar_datapath_v1."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


DESIGN_DIR = Path(__file__).resolve().parents[1]
RTL = DESIGN_DIR / "src" / "crossbar_datapath_v1.sv"
TB = DESIGN_DIR / "test" / "tb_crossbar_datapath_v1.sv"


class CrossbarDatapathRTLTests(unittest.TestCase):
    def test_deterministic_randomized_regression(self) -> None:
        iverilog = shutil.which("iverilog")
        vvp = shutil.which("vvp")
        if iverilog is None or vvp is None:
            self.skipTest("iverilog and vvp are required for the RTL regression")

        with tempfile.TemporaryDirectory(prefix="crossbar_datapath_v1-") as work:
            sim = Path(work) / "crossbar_datapath_v1.sim"
            compile_result = subprocess.run(
                [iverilog, "-g2012", "-s", "crossbar_datapath_v1_tb", "-o", str(sim), str(RTL), str(TB)],
                cwd=DESIGN_DIR,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run(
                [vvp, str(sim)],
                cwd=DESIGN_DIR,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stdout + run_result.stderr)
            self.assertIn("PASS:", run_result.stdout)


if __name__ == "__main__":
    unittest.main()
