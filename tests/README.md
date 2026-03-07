# SIM Server Tests

Standalone SIM harness for validating Section 2 behavior before governance integration.

Run all cases:

```bash
python3 -m tests.harness.runner --root . --output-dir tests/reports
```

Run selected categories:

```bash
python3 -m tests.harness.runner --root . --categories episode_lifecycle,transcript
```

Phase 1 SIM+agents characterization:

```bash
python3 -m harness.sim_episode_runner --root . --output-dir tests/reports --mode live
```
