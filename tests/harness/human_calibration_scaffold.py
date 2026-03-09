"""Optional human-calibration scaffold for future stress validation studies.

This module is intentionally non-gating:
- It prepares data collection structures.
- It never participates in CI pass/fail gates unless explicitly invoked.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def init_session(*, output_root: Path, session_id: str, protocol_version: str, metadata: dict[str, Any] | None = None) -> Path:
    session_dir = (output_root / session_id).resolve()
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "session_id": session_id,
        "protocol_version": protocol_version,
        "created_ts": _utc_now(),
        "metadata": metadata or {},
        "non_gating": True,
    }
    (session_dir / "session_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not (session_dir / "observations.ndjson").exists():
        (session_dir / "observations.ndjson").write_text("", encoding="utf-8")
    return session_dir


def append_observation(session_dir: Path, observation: dict[str, Any]) -> None:
    row = dict(observation)
    row.setdefault("ts", _utc_now())
    with (session_dir / "observations.ndjson").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def finalize_session(session_dir: Path) -> dict[str, Any]:
    ndjson = session_dir / "observations.ndjson"
    observations: list[dict[str, Any]] = []
    for line in ndjson.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            observations.append(obj)

    by_incident: dict[str, int] = {}
    by_channel: dict[str, int] = {}
    for row in observations:
        incident = str(row.get("incident_id", "unknown"))
        by_incident[incident] = int(by_incident.get(incident, 0)) + 1
        channel = str(row.get("channel", "unknown"))
        by_channel[channel] = int(by_channel.get(channel, 0)) + 1

    summary = {
        "session_id": session_dir.name,
        "generated_ts": _utc_now(),
        "non_gating": True,
        "observation_count": len(observations),
        "by_incident": by_incident,
        "by_channel": by_channel,
    }
    (session_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with (session_dir / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["session_id", "observation_count", "incident_id", "incident_count"])
        writer.writeheader()
        for incident_id, count in sorted(by_incident.items()):
            writer.writerow(
                {
                    "session_id": session_dir.name,
                    "observation_count": len(observations),
                    "incident_id": incident_id,
                    "incident_count": count,
                }
            )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Human calibration scaffold (optional, non-gating).")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--protocol-version", default="v0")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()

    session_dir = init_session(
        output_root=Path(args.output_root).resolve(),
        session_id=str(args.session_id),
        protocol_version=str(args.protocol_version),
    )
    if args.finalize:
        summary = finalize_session(session_dir)
        print(f"finalized session={summary['session_id']} observation_count={summary['observation_count']}")
    else:
        print(f"initialized session_dir={session_dir}")


if __name__ == "__main__":
    main()
