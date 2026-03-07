"""Persist per-case artifacts and aggregate reports for SIM harness."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_case_artifacts(run_dir: Path, test_id: str, case: dict[str, Any], result: dict[str, Any], discrepancy: str) -> None:
    case_dir = run_dir / test_id
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    (case_dir / "outcome.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (case_dir / "assertion.txt").write_text(discrepancy or "pass", encoding="utf-8")


def write_reports(output_dir: Path, run_id: str, rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "sim_harness_results.json"
    csv_path = output_dir / "sim_harness_summary.csv"
    report_path = output_dir / "sim_harness_report.json"

    payload = {
        "run_id": run_id,
        "total": len(rows),
        "passed": sum(1 for r in rows if r["passed"]),
        "failed": sum(1 for r in rows if not r["passed"]),
        "results": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["test_id", "category", "passed", "duration_ms", "discrepancy"])
        writer.writeheader()
        writer.writerows(
            {
                "test_id": r["test_id"],
                "category": r["category"],
                "passed": r["passed"],
                "duration_ms": r["duration_ms"],
                "discrepancy": r["discrepancy"],
            }
            for r in rows
        )

    category_totals: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = category_totals.setdefault(row["category"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        if row["passed"]:
            bucket["passed"] += 1

    report_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "category_totals": category_totals,
                "overall_pass_rate": (payload["passed"] / payload["total"] if payload["total"] else 0.0),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
