from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.harness.human_calibration_scaffold import append_observation, finalize_session, init_session


class TestHumanCalibrationScaffold(unittest.TestCase):
    def test_non_gating_session_collection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            session_dir = init_session(
                output_root=root,
                session_id="hc_001",
                protocol_version="v0",
                metadata={"operator_type": "human"},
            )
            append_observation(
                session_dir,
                {
                    "incident_id": "INC-1",
                    "channel": "voice",
                    "turn": 1,
                    "note": "operator asked location",
                },
            )
            append_observation(
                session_dir,
                {
                    "incident_id": "INC-1",
                    "channel": "voice_plus_media",
                    "turn": 2,
                    "note": "operator requested media",
                },
            )
            summary = finalize_session(session_dir)
            self.assertTrue(bool(summary.get("non_gating")))
            self.assertEqual(int(summary.get("observation_count", 0)), 2)
            self.assertEqual(int(summary.get("by_incident", {}).get("INC-1", 0)), 2)
            self.assertTrue((session_dir / "summary.csv").exists())


if __name__ == "__main__":
    unittest.main()
