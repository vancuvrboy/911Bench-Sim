from __future__ import annotations

import unittest
from pathlib import Path

from sim_server import SimulationEngine
from sim_server.schema_utils import load_json


def _caller() -> dict:
    return load_json(Path(__file__).resolve().parents[1] / "fixtures" / "caller_cooperative_calm.json")


def _incident_with_degradation() -> dict:
    incident = load_json(Path(__file__).resolve().parents[1] / "fixtures" / "incident_fire_residential.json")
    incident["id"] = "INC-FIRE-DEGRADE-001"
    incident["calltaker_degradation_config"] = {
        "enabled": True,
        "degradation_seed": 7,
        "omission_probability": 1.0,
        "dispatch_delay_probability": 1.0,
        "dispatch_delay_turns": 1,
        "verification_skip_probability": 1.0,
        "turn_time_budget_ms": 1000,
        "base_turn_cost_ms": 2200,
        "cad_field_cost_ms": 600,
        "interruption_penalty_ms": 800,
    }
    return incident


class TestDegradationEngine(unittest.TestCase):
    def test_deterministic_degradation_events_and_dispatch_release(self) -> None:
        engine = SimulationEngine(execution_id="sim-degrade-test")
        caller = _caller()
        incident = _incident_with_degradation()
        qa = load_json(Path(__file__).resolve().parents[1] / "fixtures" / "qaTemplate_003.json")
        engine.admin_load_scenario(
            scenario_id="degrade_scenario",
            caller_json=caller,
            incident_json=incident,
            qa_template_id="003",
            qa_template_json=qa,
        )
        engine.episode_start(incident_id=incident["id"])

        engine.caller_post_turn(incident["id"], "There is a fire at 2421 Main.", metadata={"stressor_markers": ["interruption"], "stress_level": 3})
        engine.calltaker_post_turn(
            incident["id"],
            text="Dispatching now and recording location.",
            cad_updates={"dispatch_triggered": True, "location": "2421 Main Street"},
        )

        # One more turn to allow delayed dispatch release.
        engine.caller_post_turn(incident["id"], "Please hurry.")
        engine.calltaker_post_turn(incident["id"], text="Stay on the line.")
        engine.episode_end(incident["id"], reason="test_complete")

        events = engine.episode_events(incident["id"])
        markers = [e.get("marker") for e in events if e.get("event_type") == "degradation_applied"]
        self.assertIn("omission_injected", markers)
        self.assertIn("verification_skipped", markers)
        self.assertIn("dispatch_delay_injected", markers)
        self.assertIn("dispatch_delay_released", markers)
        self.assertIn("time_pressure", markers)

        tool_calls = [e for e in events if e.get("event_type") == "tool_call"]
        self.assertGreaterEqual(len(tool_calls), 1)
        first_args = tool_calls[0].get("args", {}).get("cad_updates", {})
        self.assertNotIn("location", first_args)
        self.assertFalse(bool(first_args.get("dispatch_triggered", False)))

        system_subtypes = [e.get("subtype") for e in events if e.get("event_type") == "system"]
        self.assertIn("responders_dispatched", system_subtypes)


if __name__ == "__main__":
    unittest.main()
