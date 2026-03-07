# 911Bench-Sim Phase 1 Checkpoint Report (2026-03-07)

## Scope

This checkpoint captures standalone SIM+agents integration status before governance-side standalone integration.

## Commands Executed

```bash
python3 -m harness.sim_episode_runner --root . --output-dir tests/reports/checkpoint_20260307/live --mode live
python3 -m harness.sim_episode_runner --root . --output-dir tests/reports/checkpoint_20260307/record --mode record
python3 -m harness.sim_episode_runner --root . --output-dir tests/reports/checkpoint_20260307/replay --mode replay
python3 -m tests.harness.phase1_validation --root . --output-dir tests/reports
python3 -m tests.harness.runner --root . --output-dir tests/reports
```

## Results Summary

- `tests.harness.phase1_validation`: **27/27 passed**
- `tests.harness.runner` (all categories): **93/120 passed**
  - Core SIM categories passed (non-agent scripted harness): `cad_occ`, `checkpoint`, `e2e`, `episode_lifecycle`, `termination`, `event_logger`, `seed_validation`, `southbound`, `transcript`
  - `phase1_agents` in this runner: **0/27 passed** due to harness shape mismatch (details below), not engine/agent functional regressions

## Determinism and Replay Verification

Using mode-separated summaries in `tests/reports/checkpoint_20260307`:

- Scenarios verified: `phase1_fire`, `phase1_police`, `phase1_ems`
- `normalized_events_hash` matches across `live`, `record`, and `replay` for all three scenarios
- Determinism result: **PASS**

Per-scenario hashes:

- `phase1_fire`: `630593adaf429d9c51cf2ae6142471f15e72888043390e74866d3fb3904a7a66`
- `phase1_police`: `bf867242bedf0cc4196a993240f2e6f163a84b8b67f9fd423fc74d245dc52bba`
- `phase1_ems`: `34aacae65255f6ab4000aa53ea166b059a5bb2844fbc8cc34a2055d1108f3dca`

## Key Behavioral Checks Confirmed

- Event schema validation remains true in SIM+agents summaries (`all_schema_valid: true`)
- Dispatch behavior stable across scenarios (`dispatch_turn: 2` in all three core episodes)
- QA scoring deterministic and stable in baseline scenarios (`100.0` in all three core episodes)
- Console mixed-mode fixes validated indirectly by unchanged Phase 1 suite results

## Harness Gap / Clarification

`tests.harness.runner` currently loads `tests/cases/phase1_agent_cases.json`, where phase1 agent cases are metadata-only entries (no `script`, no `expected`).  
The scripted runner expects explicit step scripts, so those 27 entries fail with `incident_id not found:`.

Implication:

- The failing `phase1_agents` block in `tests.harness.runner` is a **harness-shape integration gap**, not a SIM engine regression.
- Phase 1 agent functionality is validated by `tests.harness.phase1_validation` (27/27 green) and by deterministic replay hash equality.

## Artifact Locations

- Phase 1 validation summary:
  - `tests/reports/sim_phase1_validation.json`
  - `tests/reports/sim_phase1_validation.csv`
- Scripted harness summary:
  - `tests/reports/sim_harness_report.json`
  - `tests/reports/sim_harness_results.json`
  - `tests/reports/sim_harness_summary.csv`
- Mode-separated replay checkpoint:
  - `tests/reports/checkpoint_20260307/live/sim_agents_summary.json`
  - `tests/reports/checkpoint_20260307/record/sim_agents_summary.json`
  - `tests/reports/checkpoint_20260307/replay/sim_agents_summary.json`

## Checkpoint Conclusion

Standalone SIM+agents Phase 1 is ready to proceed to the next integration stage, with one explicit backlog item:

- Align `tests/cases/phase1_agent_cases.json` with scripted runner format (or gate that category out of `tests.harness.runner` and keep `phase1_validation` as canonical for SIM-AGT coverage).
