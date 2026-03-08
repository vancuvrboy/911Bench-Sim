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

Phase 1 SIM-AGT validation suite:

```bash
python3 -m tests.harness.phase1_validation --root . --output-dir tests/reports
```

Southbound integration server (for governance integration harnesses):

```bash
python3 -m sim_server.southbound_server --root . --port 8300
```
