"""Load SIM harness JSON test cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_cases(cases_dir: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(cases_dir.glob("*.json")):
        if path.name.endswith(".schema.json"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            cases.extend(payload)
        else:
            cases.append(payload)
    return cases
