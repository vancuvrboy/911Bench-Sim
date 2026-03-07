"""Standalone SIM server validation harness runner."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

from sim_server import SimulationEngine
from sim_server.errors import SimError
from sim_server.schema_utils import load_json
from sim_server.shims import GovernanceShim, RoleClientShim
from tests.harness.artifacts import write_case_artifacts, write_reports
from tests.harness.assertions import AssertionMismatch, assert_expected
from tests.harness.event_validator import parse_ndjson, validate_event_stream
from tests.harness.test_cases import load_cases


class Harness:
    def __init__(self, root: Path, output_dir: Path) -> None:
        self.root = root
        self.output_dir = output_dir
        self.run_id = dt.datetime.now().strftime("sim_run_%Y%m%d_%H%M%S")
        self.run_dir = self.output_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def run(self, categories: set[str] | None = None) -> list[dict[str, Any]]:
        cases = load_cases(self.root / "tests" / "cases")
        rows: list[dict[str, Any]] = []
        for case in cases:
            category = case.get("category", "unknown")
            if categories and category not in categories:
                continue
            rows.append(self._run_case(case))

        write_reports(self.output_dir, self.run_id, rows)
        return rows

    def _run_case(self, case: dict[str, Any]) -> dict[str, Any]:
        test_id = case.get("test_id", "UNKNOWN")
        category = case.get("category", "unknown")
        start = time.perf_counter()
        discrepancy = ""
        passed = False
        outcome: dict[str, Any] = {}

        try:
            outcome = self._execute_script(case)
            assert_expected(outcome, case.get("expected", {}))
            passed = True

            if case.get("deterministic", False):
                replay = self._execute_script(case)
                norm_a = json.dumps(_normalize(outcome), sort_keys=True)
                norm_b = json.dumps(_normalize(replay), sort_keys=True)
                if norm_a != norm_b:
                    passed = False
                    discrepancy = "deterministic_replay_mismatch"
        except (AssertionMismatch, SimError) as exc:
            expected_error = case.get("expected", {}).get("error_contains")
            if expected_error and expected_error in str(exc):
                passed = True
            else:
                discrepancy = str(exc)
        except Exception as exc:  # pragma: no cover
            discrepancy = f"error:{exc}"

        duration_ms = int((time.perf_counter() - start) * 1000)
        row = {
            "test_id": test_id,
            "category": category,
            "passed": passed,
            "duration_ms": duration_ms,
            "discrepancy": discrepancy,
            "outcome": outcome,
        }
        write_case_artifacts(self.run_dir, test_id, case, row, discrepancy)
        return row

    def _execute_script(self, case: dict[str, Any]) -> dict[str, Any]:
        engine = SimulationEngine(execution_id=case.get("execution_id", "sim-harness"))
        gov = GovernanceShim(engine)
        role = RoleClientShim(engine)

        scenario = case.get("scenario", {})
        incident_id = ""
        latest_request_id = ""

        for step in case.get("script", []):
            action = step.get("action")
            if action == "load_scenario":
                caller_json = load_json(self.root / step.get("caller_json", scenario.get("caller_json", "fixtures/caller_cooperative_calm.json")))
                incident_json = load_json(self.root / step.get("incident_json", scenario.get("incident_json", "fixtures/incident_fire_residential.json")))
                qa_json = load_json(self.root / step.get("qa_template_json", scenario.get("qa_template_json", "fixtures/qaTemplate_003.json")))
                response = engine.admin_load_scenario(
                    scenario_id=step.get("scenario_id", scenario.get("scenario_id", "default")),
                    caller_json=caller_json,
                    incident_json=incident_json,
                    qa_template_id=step.get("qa_template_id", scenario.get("qa_template_id", "NENA-v003")),
                    qa_template_json=qa_json,
                )
                incident_id = response["incident_id"]
            elif action == "start_episode":
                engine.episode_start(incident_id)
            elif action == "caller_turn":
                role.caller_turn(incident_id=incident_id, text=step["text"], metadata=step.get("metadata"))
            elif action == "calltaker_turn":
                role.calltaker_turn(incident_id=incident_id, text=step["text"], cad_updates=step.get("cad_updates"))
            elif action == "governance_patch":
                gov.apply_cad_patch(
                    incident_id=incident_id,
                    action_id=step.get("action_id", "action-1"),
                    action_class=step.get("action_class", "cad_update.address"),
                    payload=step.get("payload", {}),
                    read_set=step.get("read_set", {"record_version": 0, "field_versions": {}}),
                    checkpoint_ref=step.get("checkpoint_ref"),
                    checkpoint_decision=step.get("checkpoint_decision"),
                )
            elif action == "checkpoint_request":
                req = gov.request_checkpoint(incident_id=incident_id, request=step["request"])
                latest_request_id = req["request_id"]
            elif action == "checkpoint_submit":
                engine.checkpoint_submit(
                    request_id=step.get("request_id", latest_request_id),
                    decision=step["decision"],
                    edited_payload=step.get("edited_payload"),
                    re_escalate_to=step.get("re_escalate_to"),
                    rationale=step.get("rationale"),
                )
            elif action == "checkpoint_poll":
                engine.checkpoint_poll(step.get("request_id", latest_request_id))
            elif action == "emit_event":
                payload = dict(step["event"])
                payload.setdefault("incident_id", incident_id)
                gov.emit_event(payload)
            elif action == "end_call":
                role.end_call(incident_id=incident_id, reason=step["reason"], reason_detail=step.get("reason_detail"))
            elif action == "end_episode":
                engine.episode_end(incident_id=incident_id, reason=step.get("reason", "test_complete"))

        events_blob = engine.artifact_get(incident_id=incident_id, name="_events.ndjson")["content"]
        events = parse_ndjson(events_blob)
        schema_errors = validate_event_stream(events)

        snapshot = engine.plant_get_state_snapshot(incident_id)
        return {
            "status": "ok",
            "incident_id": incident_id,
            "episode_sealed": snapshot["episode_phase"] == "sealed",
            "event_count": len(events),
            "event_types": [e.get("event_type") for e in events],
            "final_cad_state": snapshot["cad_state"],
            "final_record_version": snapshot["record_version"],
            "events_schema_valid": len(schema_errors) == 0,
            "schema_errors": schema_errors,
        }


def _normalize(outcome: dict[str, Any]) -> dict[str, Any]:
    obj = json.loads(json.dumps(outcome))
    obj["incident_id"] = "<normalized>"
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description="Run standalone 911Bench SIM harness")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-dir", default="tests/reports")
    parser.add_argument("--categories", default="", help="Comma-separated categories")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = (root / args.output_dir).resolve()

    categories = {c.strip() for c in args.categories.split(",") if c.strip()} or None

    harness = Harness(root=root, output_dir=output)
    rows = harness.run(categories=categories)

    total = len(rows)
    passed = sum(1 for row in rows if row["passed"])
    print(f"SIM harness complete: passed {passed}/{total}")
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
