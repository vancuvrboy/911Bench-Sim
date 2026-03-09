from __future__ import annotations

import unittest

from tests.harness.experiment_runner import _expand_scenarios


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


if __name__ == "__main__":
    unittest.main()
