import unittest

from src.config_schema import ConfigError, effective_config_hash, preflight_config


class ConfigSchemaTests(unittest.TestCase):
    def test_accepts_pinned_knobs_and_rejects_legacy_padding(self):
        self.assertEqual(preflight_config({"GPL_CELL_PADDING": 2})["GPL_CELL_PADDING"], 2)
        with self.assertRaises(ConfigError):
            preflight_config({"CELL_PAD": 2})

    def test_bounds_types_and_protected_inputs(self):
        with self.assertRaises(ConfigError):
            preflight_config({"FP_CORE_UTIL": 101})
        with self.assertRaises(ConfigError):
            preflight_config({"CLOCK_PERIOD": "20"})
        baseline = {"CLOCK_PORT": "clk", "VERILOG_FILES": "rtl.sv", "DIE_AREA": [0, 0, 10, 10]}
        with self.assertRaises(ConfigError):
            preflight_config({"CLOCK_PORT": "bad"}, baseline)
        self.assertEqual(preflight_config({"CLOCK_PORT": "clk"}, baseline)["CLOCK_PORT"], "clk")

    def test_synthesis_strategy_is_legal_and_bounded(self):
        self.assertEqual(preflight_config({"SYNTH_STRATEGY": "AREA 2"})["SYNTH_STRATEGY"], "AREA 2")
        with self.assertRaises(ConfigError):
            preflight_config({"SYNTH_STRATEGY": "AREA 9"})

    def test_hash_is_canonical(self):
        self.assertEqual(effective_config_hash({"A": 1, "B": 2}), effective_config_hash({"B": 2, "A": 1}))


if __name__ == "__main__":
    unittest.main()
