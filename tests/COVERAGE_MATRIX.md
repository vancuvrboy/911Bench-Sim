# 911Bench-Sim Coverage Matrix

This matrix maps SIM test plan Section 4 IDs to implemented case files.

## Category Coverage

- `episode_lifecycle`: `LIFE-001` .. `LIFE-012` (`tests/cases/episode_lifecycle_cases.json`)
- `transcript`: `TXPT-001` .. `TXPT-008` (`tests/cases/transcript_engine_cases.json`)
- `cad_occ`: `CAD-001` .. `CAD-010` (`tests/cases/cad_occ_cases.json`)
- `checkpoint`: `CHKP-001` .. `CHKP-015` (`tests/cases/checkpoint_service_cases.json`)
- `termination`: `TERM-001` .. `TERM-015` (`tests/cases/episode_termination_cases.json`)
- `event_logger`: `EVNT-001` .. `EVNT-011` (`tests/cases/event_logger_cases.json`)
- `southbound`: `SBND-001` .. `SBND-007` (`tests/cases/southbound_tools_cases.json`)
- `seed_validation`: `SEED-001` .. `SEED-007` (`tests/cases/seed_validation_cases.json`)
- `e2e`: `E2E-001` .. `E2E-008` (`tests/cases/e2e_scripted_cases.json`)

## Execution Command

```bash
python3 -m tests.harness.runner --root . --output-dir tests/reports
```

## Current Baseline Result

- Total cases: `93`
- Pass: `93`
- Fail: `0`
