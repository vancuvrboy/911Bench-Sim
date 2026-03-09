from __future__ import annotations

import unittest
from pathlib import Path

from agents.provider import OpenAISyntheticCallTakerAgent
from sim_server import SimulationEngine
from sim_server.schema_utils import load_json


class TestStressTranscriptAndMedia(unittest.TestCase):
    def test_consecutive_interruption_caller_turns_merge_and_silent_tag(self) -> None:
        engine = SimulationEngine(execution_id="sim-transcript-stress")
        caller = load_json(Path(__file__).resolve().parents[1] / "fixtures" / "caller_cooperative_calm.json")
        incident = load_json(Path(__file__).resolve().parents[1] / "fixtures" / "incident_fire_residential.json")
        incident["id"] = "INC-FIRE-STRESS-MERGE-001"
        qa = load_json(Path(__file__).resolve().parents[1] / "fixtures" / "qaTemplate_003.json")

        engine.admin_load_scenario(
            scenario_id="stress_merge",
            caller_json=caller,
            incident_json=incident,
            qa_template_id="003",
            qa_template_json=qa,
        )
        engine.episode_start(incident_id=incident["id"])

        # First caller fragment.
        engine.caller_post_turn(
            incident_id=incident["id"],
            text="There is a fire.",
            metadata={"stress_level": 2},
        )
        # Interruption follow-up fragment on same turn.
        engine.caller_post_turn(
            incident_id=incident["id"],
            text="Please listen!",
            metadata={"stress_level": 2, "stressor_markers": ["interruption"]},
        )
        engine.calltaker_post_turn(incident_id=incident["id"], text="What is your exact location?")

        # Explicit silent caller turn.
        engine.caller_post_turn(
            incident_id=incident["id"],
            text="",
            metadata={"stress_level": 3, "stressor_markers": ["non_responsive"]},
        )
        engine.calltaker_post_turn(incident_id=incident["id"], text="Can you hear me?")
        engine.episode_end(incident["id"], reason="test_complete")

        events = engine.episode_events(incident["id"])
        conv = [e for e in events if e.get("event_type") == "conversation"]
        self.assertEqual(len(conv), 2)
        self.assertIn("There is a fire.\nPlease listen!", str(conv[0].get("caller", "")))

        sys_silent = [e for e in events if e.get("event_type") == "system" and e.get("subtype") == "silent_turn"]
        self.assertGreaterEqual(len(sys_silent), 1)

    def test_receive_media_tool_returns_deterministic_payload(self) -> None:
        agent = object.__new__(OpenAISyntheticCallTakerAgent)
        agent.incident_json = {
            "id": "INC-FIRE-MEDIA-001",
            "ng911_media": [
                {
                    "media_id": "m1",
                    "type": "image",
                    "description": "Photo showing flames from second floor window.",
                    "valence": "high_risk",
                    "payload": {"visible_smoke": True, "occupants_visible": False},
                }
            ],
        }
        agent.qa_template_json = {}
        agent.enable_map_tool = True
        agent.enable_media_tool = True
        agent._pending_updates = {}
        agent._pending_end_call = {}
        agent._pending_checkpoint_decisions = []
        agent._pending_checkpoints = []

        specs = agent._tool_specs()
        names = {str((s.get("function") or {}).get("name", "")) for s in specs}
        self.assertIn("calltaker.receive_media", names)

        out = agent._exec_tool(
            "calltaker.receive_media",
            {"incident_id": "INC-FIRE-MEDIA-001", "media_id": "m1"},
            cad_state={},
            system_events=[],
        )
        self.assertEqual(out.get("media_id"), "m1")
        self.assertEqual(out.get("media", {}).get("type"), "image")
        self.assertEqual(out.get("media", {}).get("valence"), "high_risk")


if __name__ == "__main__":
    unittest.main()
