from __future__ import annotations

import unittest
from pathlib import Path

from agents.caller_agent import CallerAgent
from sim_server import SimulationEngine
from sim_server.errors import ValidationError
from sim_server.schema_utils import load_json, validate_seed_triplet


def _caller_seed() -> dict:
    return {
        "version": "1.0",
        "profile_id": "CALLER-STRESS-001",
        "profile_name": "Stress Test Caller",
        "identity": {
            "name": "Jamie Lee",
            "age": 34,
            "gender": "Female",
            "pronouns": "she/her",
            "phone_number": "+1-604-555-0112",
            "home_city": "Vancouver",
        },
        "language": {"primary": "English"},
        "accessibility": {"hearing": "none", "vision": "none", "mobility": "independent"},
        "emotional_baseline": "Anxious",
        "speech": {"rate": "Moderate", "clarity": "High", "disfluencies": []},
        "interaction_style": {
            "interrupts_operator": False,
            "waits_for_questions": True,
            "volunteers_key_facts": True,
            "asks_for_confirmation": True,
        },
        "instruction_following": {"compliance_level": "High", "stays_on_line": True, "will_meet_responders": True},
        "disclosure_policy": {"name": "on_ask_once", "current_location": "on_ask_once", "callback_number": "on_ask_once"},
        "memory_reliability": {"omission_rate": "Low", "contradiction_rate": "Low", "precision_level": "High"},
        "opening_style": "Factual one-sentence summary",
        "example_short_answers": {"name": "Jamie Lee", "callback_number": "+1-604-555-0112"},
    }


def _incident_seed() -> dict:
    return {
        "id": "INC-FIRE-STRESS-001",
        "type": "Fire",
        "location": {"address_line": "2421 Main Street", "city": "Vancouver"},
        "caller_view": {"initial_opening_line": "There is a fire at 2421 Main."},
        "first_responder_delay": 8,
        "max_turns": 20,
    }


class TestCallerStressBehavior(unittest.TestCase):
    def test_deterministic_stressor_hooks(self) -> None:
        caller = _caller_seed()
        caller["stressor_config"] = {
            "stress_level": 4,
            "seed": 123,
            "interruption_policy": {"enabled": True, "turn_offsets": [2, 4], "probability": 0.0, "fragment": "Wait, listen!"},
            "non_responsive_policy": {
                "enabled": True,
                "turn_offsets": [3],
                "probability": 0.0,
                "mode": "non_verbal",
                "non_verbal_text": "...heavy breathing...",
            },
            "contradiction_policy": {
                "enabled": True,
                "turn_offsets": [4],
                "probability": 0.0,
                "field": "current_location",
                "text": "Actually maybe the address is wrong.",
            },
            "topic_digression_policy": {
                "enabled": True,
                "turn_offsets": [2],
                "probability": 0.0,
                "text": "Please hurry, I am panicking.",
            },
        }
        incident = _incident_seed()
        prompts = [
            "Police, Fire, or Ambulance?",
            "What is your exact address?",
            "Can you repeat that?",
            "Confirm your location once more.",
        ]

        a1 = CallerAgent(caller_json=caller, incident_json=incident)
        a2 = CallerAgent(caller_json=caller, incident_json=incident)

        out1 = [a1.next_turn(p, []) for p in prompts]
        out2 = [a2.next_turn(p, []) for p in prompts]
        self.assertEqual(out1, out2)

        turn2_text, turn2_meta = out1[1]
        self.assertIn("Please hurry, I am panicking.", turn2_text)
        self.assertIn("Wait, listen!", turn2_text)
        self.assertEqual(set(turn2_meta.get("stressor_markers", [])), {"topic_digression", "interruption"})

        turn3_text, turn3_meta = out1[2]
        self.assertEqual(turn3_text, "...heavy breathing...")
        self.assertEqual(turn3_meta.get("stressor_markers"), ["non_responsive"])

        turn4_text, turn4_meta = out1[3]
        self.assertIn("Actually maybe the address is wrong.", turn4_text)
        self.assertIn("interruption", turn4_meta.get("stressor_markers", []))
        self.assertIn("contradiction", turn4_meta.get("stressor_markers", []))

    def test_engine_emits_stressor_applied_events(self) -> None:
        caller = _caller_seed()
        caller["stressor_config"] = {
            "stress_level": 2,
            "seed": 999,
            "interruption_policy": {"enabled": True, "turn_offsets": [1], "probability": 0.0, "fragment": "Please listen."},
            "non_responsive_policy": {"enabled": False, "probability": 0.0},
            "contradiction_policy": {"enabled": False, "probability": 0.0},
            "topic_digression_policy": {"enabled": False, "probability": 0.0},
        }
        incident = _incident_seed()
        qa_template = load_json(Path(__file__).resolve().parents[1] / "fixtures" / "qaTemplate_003.json")

        agent = CallerAgent(caller_json=caller, incident_json=incident)
        engine = SimulationEngine(execution_id="sim-stress-test")
        engine.admin_load_scenario(
            scenario_id="stress_scenario",
            caller_json=caller,
            incident_json=incident,
            qa_template_id="003",
            qa_template_json=qa_template,
        )
        engine.episode_start(incident_id=incident["id"])

        caller_text, caller_meta = agent.next_turn("Police, Fire, or Ambulance?", [])
        engine.caller_post_turn(incident_id=incident["id"], text=caller_text, metadata=caller_meta)
        engine.calltaker_post_turn(incident_id=incident["id"], text="What is your location?")
        engine.episode_end(incident_id=incident["id"], reason="test_complete")

        events = engine.episode_events(incident["id"])
        stress_events = [e for e in events if e.get("event_type") == "stressor_applied"]
        self.assertGreaterEqual(len(stress_events), 1)
        self.assertEqual(stress_events[0].get("marker"), "interruption")
        self.assertEqual(int(stress_events[0].get("stress_level", -1)), 2)

    def test_seed_validation_rejects_invalid_stress_level(self) -> None:
        caller = _caller_seed()
        caller["stressor_config"] = {"stress_level": 9}
        incident = _incident_seed()
        qa_template = {"templates": {"COMMON": {"sections": []}}}
        with self.assertRaises(ValidationError):
            validate_seed_triplet(caller, incident, qa_template)


if __name__ == "__main__":
    unittest.main()
