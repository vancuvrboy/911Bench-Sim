from __future__ import annotations

import unittest

from sim_server.qa_pipeline import _section_order, build_qa_input


class TestQAStressInput(unittest.TestCase):
    def test_stress_events_included_in_qa_input(self) -> None:
        events = [
            {
                "event_type": "meta",
                "event_seq": 0,
                "ts": "2026-03-09T00:00:00Z",
                "scenario_id": "s1",
                "incident_id": "INC-1",
                "incident_type": "Fire",
                "qa_template_id": "003",
            },
            {
                "event_type": "conversation",
                "event_seq": 1,
                "ts": "2026-03-09T00:00:01Z",
                "turn": 1,
                "call_taker": "911, what is your emergency?",
                "caller": "There is a fire.",
            },
            {
                "event_type": "stressor_applied",
                "event_seq": 2,
                "ts": "2026-03-09T00:00:02Z",
                "turn": 1,
                "marker": "interruption",
                "stress_level": 3,
                "detail": {"fragment": "listen!"},
            },
            {
                "event_type": "degradation_applied",
                "event_seq": 3,
                "ts": "2026-03-09T00:00:03Z",
                "turn": 1,
                "marker": "omission_injected",
                "detail": {"dropped_field": "location"},
            },
        ]
        qa_template = {"version": "003", "templates": {"COMMON": {"sections": []}}}
        qa_input = build_qa_input(events=events, qa_template=qa_template, incident_type="Fire")
        self.assertEqual(int(qa_input["metrics"]["stress_event_count"]), 2)
        self.assertEqual(len(qa_input["stress_events"]), 2)
        self.assertEqual(qa_input["stress_events"][0]["marker"], "interruption")

    def test_section_order_dedupes_duplicate_section_names(self) -> None:
        qa_template = {
            "templates": {
                "COMMON": {"sections": [{"name": "Telephone Protocol / Skills"}]},
                "FIRE": {"sections": [{"name": "Telephone Protocol / Skills"}]},
            }
        }
        qa_score = {"incident_type": "FIRE"}
        order = _section_order(qa_template, qa_score)
        self.assertEqual(order, ["Telephone Protocol / Skills"])


if __name__ == "__main__":
    unittest.main()
