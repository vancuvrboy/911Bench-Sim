"""Expectation checks for SIM tests."""

from __future__ import annotations

from typing import Any


class AssertionMismatch(Exception):
    pass


def assert_expected(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if "status" in expected and actual.get("status") != expected["status"]:
        raise AssertionMismatch(f"status_mismatch:{actual.get('status')}!= {expected['status']}")

    if "episode_sealed" in expected:
        if bool(actual.get("episode_sealed")) != bool(expected["episode_sealed"]):
            raise AssertionMismatch("episode_sealed_mismatch")

    if "event_count_min" in expected and int(actual.get("event_count", 0)) < int(expected["event_count_min"]):
        raise AssertionMismatch("event_count_too_low")

    if "event_types_present" in expected:
        present = set(actual.get("event_types", []))
        missing = [name for name in expected["event_types_present"] if name not in present]
        if missing:
            raise AssertionMismatch(f"missing_event_types:{','.join(missing)}")

    if "final_record_version_min" in expected:
        if int(actual.get("final_record_version", 0)) < int(expected["final_record_version_min"]):
            raise AssertionMismatch("final_record_version_too_low")

    if "events_schema_valid" in expected:
        if bool(expected["events_schema_valid"]) != bool(actual.get("events_schema_valid", False)):
            raise AssertionMismatch("events_schema_valid_mismatch")

    if "final_cad_state" in expected:
        target = expected["final_cad_state"]
        actual_state = actual.get("final_cad_state", {})
        for key, value in target.items():
            if actual_state.get(key) != value:
                raise AssertionMismatch(f"final_cad_state_mismatch:{key}")
