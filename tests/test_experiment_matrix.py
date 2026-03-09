from __future__ import annotations

import unittest

from tests.harness.experiment_runner import _expand_scenarios, _scenario_seed_overrides


class TestExperimentMatrixExpansion(unittest.TestCase):
    def test_matrix_expands_placeholders(self) -> None:
        manifest = {
            "experiment_id": "stress_matrix",
            "matrix": {
                "level": [0, 2],
                "channel": ["voice", "voice_plus_media"],
            },
            "scenarios": [
                {
                    "scenario_name": "fire_l{level}_{channel}",
                    "caller_file": "fixtures/caller_cooperative_calm.json",
                    "incident_file": "fixtures/incident_fire_residential.json",
                    "qa_file": "fixtures/qaTemplate_003.json",
                    "stress_level": "{level}",
                    "channel": "{channel}",
                }
            ],
        }
        rows = _expand_scenarios(manifest)
        self.assertEqual(len(rows), 4)
        names = {row["scenario_name"] for row in rows}
        self.assertIn("fire_l0_voice", names)
        self.assertIn("fire_l2_voice_plus_media", names)

    def test_seed_overrides_from_stress_and_channel(self) -> None:
        caller_ovr, incident_ovr = _scenario_seed_overrides({"stress_level": "3", "channel": "voice_plus_media"})
        self.assertEqual(int(caller_ovr["stressor_config"]["stress_level"]), 3)
        self.assertTrue(bool(incident_ovr["calltaker_degradation_config"]["enabled"]))
        self.assertEqual(int(incident_ovr["calltaker_degradation_config"]["stress_level"]), 3)
        self.assertTrue(isinstance(incident_ovr.get("ng911_media"), list) and len(incident_ovr["ng911_media"]) >= 1)


if __name__ == "__main__":
    unittest.main()
