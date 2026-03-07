# 911Bench-Sim

Standalone SIM server repository for 911Bench Section 2 development.

## Shared baseline copied from 911Bench
- `schemas/`
- `design_docs/911Bench_Architecture_v4.docx`
- `design_docs/911Bench_Sim_Server_Test_Plan.docx`
- `.github/workflows/ci.yml`
- `.gitignore`
- `requirements.lock`

## Local structure
- `sim_server/` (SIM runtime and interfaces)
- `agents/` (Phase 1 caller, call-taker, QA deterministic agents)
- `harness/` (Phase 1 orchestration runners)
- `tests/` (SIM test harness and cases)
- `fixtures/sim/` (SIM scenarios and plant state fixtures)

## Phase 1: SIM + Agents

Run standalone SIM+agents episodes (Fire/Police/EMS):

```bash
python3 -m harness.sim_episode_runner --root . --output-dir tests/reports --mode live
```

Record deterministic replay fixtures:

```bash
python3 -m harness.sim_episode_runner --root . --output-dir tests/reports --mode record
```

Replay recorded fixtures:

```bash
python3 -m harness.sim_episode_runner --root . --output-dir tests/reports --mode replay
```
