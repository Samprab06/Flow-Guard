import unittest

import numpy as np

from optimizers.acquire import FROZEN_SEARCH_SPACE, MIN_FEASIBILITY_PROBABILITY, constrained_expected_improvement, select_candidate
from models.models import FROZEN_KNOBS, FeasibilityModel, FlowGuardModels


class ModelsAndAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.features = [[0.0], [1.0], [2.0], [3.0]]
        self.feasible = [True, False, True, False]
        self.area = [100.0, 1000.0, 80.0, 1000.0]
        self.wns = [0.1, -1.0, 0.2, -1.0]

    def test_four_observations_fit_and_score(self):
        models = FlowGuardModels().fit(self.features, self.feasible, self.area, self.wns)
        self.assertFalse(models.feasibility.calibrated)
        scores = constrained_expected_improvement([[0.0], [2.0]], models, best_cell_area=100.0)
        self.assertEqual(scores.shape, (2,))
        self.assertTrue(np.isfinite(scores).all())
        choice = select_candidate([[0.0], [2.0]], models, best_cell_area=100.0)
        self.assertIn(choice.index, (0, 1))

    def test_degenerate_and_tiny_classes_use_safe_fallbacks(self):
        all_feasible = FeasibilityModel().fit([[0.0], [1.0]], [True, True])
        np.testing.assert_allclose(all_feasible.predict_proba([[2.0]]), [1.0])
        tiny = FeasibilityModel().fit(self.features, self.feasible)
        self.assertFalse(tiny.calibrated)
        self.assertTrue(0.0 <= tiny.predict_proba([[0.5]])[0] <= 1.0)

    def test_risk_abstention_zeros_low_feasibility_scores(self):
        models = FlowGuardModels().fit(self.features, self.feasible, self.area, self.wns)
        models.feasibility.predict_proba = lambda values: np.array([MIN_FEASIBILITY_PROBABILITY - 0.01])
        score = constrained_expected_improvement([[2.0]], models, best_cell_area=1000.0)
        np.testing.assert_allclose(score, [0.0])

    def test_frozen_calibration_knobs(self):
        self.assertEqual(FROZEN_KNOBS.classifier_estimators, 50)
        self.assertEqual(FROZEN_KNOBS.calibration_cv, 3)

    def test_frozen_search_space(self):
        self.assertEqual(FROZEN_SEARCH_SPACE["PL_TARGET_DENSITY"], (0.40, 0.70))
        self.assertEqual(FROZEN_SEARCH_SPACE["CELL_PAD"], (1, 4))
        self.assertEqual(FROZEN_SEARCH_SPACE["SYNTH_STRATEGY"], ("AREA 0", "AREA 1", "AREA 2", "AREA 3"))
        self.assertEqual(FROZEN_SEARCH_SPACE["FP_CORE_UTIL"], (35, 60))


if __name__ == "__main__":
    unittest.main()
