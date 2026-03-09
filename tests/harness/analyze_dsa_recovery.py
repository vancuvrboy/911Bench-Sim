"""Analyze DSA recovery experiments from experiment_runner summary.csv."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _to_float(v: Any) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(v)
    except Exception:
        return None


def analyze(summary_csv: Path, baseline_profile: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with summary_csv.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(r) for r in reader]

    by_profile: dict[str, list[float]] = {}
    for row in rows:
        profile = str(row.get("dsa_profile", "")).strip() or "unspecified"
        score = _to_float(row.get("qa_score"))
        if score is None:
            continue
        by_profile.setdefault(profile, []).append(score)

    profile_stats: dict[str, dict[str, float]] = {}
    for profile, vals in sorted(by_profile.items()):
        if not vals:
            continue
        profile_stats[profile] = {
            "n": float(len(vals)),
            "mean_qa": float(sum(vals) / len(vals)),
            "min_qa": float(min(vals)),
            "max_qa": float(max(vals)),
        }

    baseline = profile_stats.get(baseline_profile)
    deltas: dict[str, float] = {}
    if baseline is not None:
        b = float(baseline.get("mean_qa", 0.0))
        for profile, stats in profile_stats.items():
            deltas[profile] = float(stats.get("mean_qa", 0.0) - b)

    return {
        "baseline_profile": baseline_profile,
        "profiles": profile_stats,
        "mean_delta_vs_baseline": deltas,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze DSA recovery experiment summary CSV.")
    parser.add_argument("--summary-csv", required=True)
    parser.add_argument("--baseline-profile", default="deterministic_911buddy_v1")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    summary_path = Path(args.summary_csv).resolve()
    result = analyze(summary_path, baseline_profile=str(args.baseline_profile))
    output_path = Path(args.output_json).resolve() if str(args.output_json).strip() else summary_path.with_name("dsa_recovery_analysis.json")
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
