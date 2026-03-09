from __future__ import annotations

import unittest

from agents.provider import OpenAIQAEvaluatorAgent
from agents.qa_agent import QAEvaluatorAgent


def _template() -> dict:
    return {
        "version": "003",
        "normalize_to": 100,
        "templates": {
            "COMMON": {
                "sections": [
                    {
                        "name": "Base",
                        "items": [
                            {"id": "base_item", "question": "Base item", "points": 10},
                        ],
                    },
                    {
                        "name": "Stress Response Quality",
                        "applies_when": {"stress_min_level": 1},
                        "items": [
                            {"id": "stress_item", "question": "Stress handling", "points": 5},
                        ],
                    },
                ]
            },
            "FIRE": {"sections": []},
        },
    }


class TestQAStressApplicability(unittest.TestCase):
    def test_deterministic_marks_stress_items_na_at_level0(self) -> None:
        agent = QAEvaluatorAgent(qa_template_json=_template())
        events = [
            {"event_type": "meta", "stress_config": {"stress_level": 0}},
            {"event_type": "conversation", "turn": 1, "call_taker": "What is the location?", "caller": "2421 Main"},
        ]
        score = agent.evaluate(events=events, incident_type="FIRE")
        by_id = {row["id"]: row for row in score["items"]}
        self.assertEqual(by_id["stress_item"]["answer"], "NA")
        self.assertEqual(float(by_id["stress_item"]["points_awarded"]), 0.0)
        self.assertEqual(float(score["total_points_possible"]), 10.0)

    def test_openai_normalizer_forces_stress_item_na_at_level0(self) -> None:
        agent = object.__new__(OpenAIQAEvaluatorAgent)
        agent.qa_template_json = _template()
        model_obj = {
            "normalized_score": 100,
            "incident_type": "FIRE",
            "items": [
                {"id": "base_item", "answer": "YES", "points_awarded": 10, "points_possible": 10, "rationale": "ok"},
                {"id": "stress_item", "answer": "YES", "points_awarded": 5, "points_possible": 5, "rationale": "ok"},
            ],
        }
        out = agent._normalize_score_payload(model_obj, incident_type="FIRE", qa_input={"stress_events": []})
        by_id = {row["id"]: row for row in out["items"]}
        self.assertEqual(by_id["stress_item"]["answer"], "NA")
        self.assertEqual(float(by_id["stress_item"]["points_awarded"]), 0.0)
        self.assertEqual(float(out["total_points_possible"]), 10.0)
        self.assertEqual(float(out["normalized_score"]), 100.0)


if __name__ == "__main__":
    unittest.main()
