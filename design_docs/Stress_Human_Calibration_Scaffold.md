# Human Calibration Scaffold (Non-Gating)

## Purpose
This scaffold prepares data collection for future human-operator stress calibration studies.

## Important Constraint
- Human calibration is **not a merge/blocking gate** at this stage.
- Current release gates remain:
  - functional correctness
  - deterministic reproducibility
  - degradation curve sanity
  - operational safety

## Scope of Scaffold
- Session manifest creation with protocol metadata.
- Observation append pipeline (`observations.ndjson`).
- End-of-session summary export (`summary.json`, `summary.csv`).

## CLI Usage
Initialize session:

```bash
python3 -m tests.harness.human_calibration_scaffold \
  --output-root /tmp/911bench-human-calibration \
  --session-id hc_20260309_a \
  --protocol-version v0
```

Finalize session:

```bash
python3 -m tests.harness.human_calibration_scaffold \
  --output-root /tmp/911bench-human-calibration \
  --session-id hc_20260309_a \
  --protocol-version v0 \
  --finalize
```

## Integration Note
When human studies begin, this scaffold can be wired into console/UI or headless orchestrators without altering current pass/fail CI semantics.
