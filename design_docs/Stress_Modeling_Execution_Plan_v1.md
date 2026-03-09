# 911Bench-Sim-S Stress Modeling Execution Plan (Phase 0)

Source specification: `911Bench/design_docs/911Bench Addendum - Cognitive Load and Stressor Modeling.docx` (Version 1.0, 2026-03-09).

## Scope Boundary
- This repo (`911Bench-Sim-S`) is the stress-modeling sandbox branch.
- Baseline repo (`911Bench-Sim`) remains unchanged until phase gates pass.
- Only simulator-side addendum items are in scope now.

## Implementation Order (from addendum section 11)
1. Caller stressor schema + caller behavior hooks
2. Call-taker degradation engine
3. NG911 media channel + `calltaker.receive_media`
4. Stress prompt library wiring
5. QA rubric/stress-aware scoring extensions
6. Simulation server event/schema changes
7. Harness stress-matrix integration
8. Human calibration protocol scaffolding (data model and hooks; not full recruitment)
9. DSA recovery experiment harness extension (after stress baseline is stable)

## Phase 1 (Immediate) Detailed Backlog

### 1) Caller-Side Stressor Config (Addendum Section 3)
- Extend caller seed schema with `stressor_config` object:
  - `stress_level` 0..5
  - interruption policy
  - non-responsive policy
  - media policy
  - threat escalation policy
  - topic digression policy
  - contradiction policy
  - language switching policy
- Implement caller orchestration behaviors:
  - controlled double-utterance interruptions
  - configured silent/non-verbal turns
  - contradiction emission at configured turn offsets
  - topic digressions and return behavior
- Acceptance:
  - stressor behavior reproducible with fixed seed
  - event log contains deterministic stressor markers

### 2) Call-Taker Degradation Engine (Addendum Section 4)
- Add call-taker config extensions:
  - `stress_level`, `stress_profile`, omission/verification/context/parse/dispatch params
  - `degradation_seed`
- Implement degradation pipeline (code-enforced):
  - omission injection (field-level)
  - verification-skip injection
  - question order perturbation (L3+)
  - context reduction (sliding window)
  - dispatch delay + parse error probabilities
- Add cumulative load model:
  - base + interruption/media/threat/silence/contradiction increments
  - threshold-triggered parameter adjustments
- Acceptance:
  - same seed + same scenario -> same degradation trace
  - `degradation_applied` events emitted with details

### 3) Simulation Server Event Extensions (Addendum Section 5)
- Add `stressor_applied` and `degradation_applied` event types
- Extend transcript engine:
  - allow consecutive caller turns when interruption flag is set
  - allow and tag silent turns
  - emit NG911 events for media attachments
- Extend `meta` event with `stress_config` block
- Acceptance:
  - schema validation passes for all new event types
  - backward compatibility with existing non-stress episodes

### 4) NG911 Media Tool (Addendum Section 3.3 + 5.3)
- Add MCP tool: `calltaker.receive_media(incident_id, media_id)`
- Return media description + valence + informational payload
- Integrate into synthetic call-taker tool loop
- Acceptance:
  - media events retrievable deterministically by media_id
  - call-taker can consume and operationalize media detail

### 5) QA Stress Section (Addendum Section 6)
- Add “Stress Response Quality” section to QA template set
- Add conditional applicability logic for stress-specific items
- Ensure scoring remains comparable while rationales include stress context
- Acceptance:
  - stress items `NA` at L0 when required
  - item-level outputs stable and traceable

### 6) Harness Stress Matrix (Addendum Section 10)
- Add stress-matrix experiment config expansion:
  - stress level x channel x incident type
  - placeholder expansion `{level}`
- Add seed strategy for reproducibility
- Produce outputs under dedicated stress experiment directory
- Acceptance:
  - reduced-N matrix run completes end-to-end
  - summary includes stress-level and channel factors

## Experiment Gates Before Merge Back to 911Bench-Sim

### Gate A: Functional Correctness
- All existing baseline tests still pass (current phase1 suite + QA rule tests)
- New stress features have dedicated tests for:
  - interruption mechanics
n  - degradation injection determinism
  - event logging schema compliance
  - media tool retrieval correctness

### Gate B: Deterministic Reproducibility
- Repeat same stress seed matrix twice -> identical normalized event hashes and equivalent QA totals.

### Gate C: Degradation Curve Sanity
- Run stress levels 0..5 (combined channel, reduced N) and confirm non-improving trend in mean QA with increasing stress (allowing small noise).

### Gate D: Operational Safety
- No regressions in episode sealing, artifact writing, and QA pipeline.
- No deadlocks in auto-run/auto-step loops under interruption/silence scenarios.

### Human Calibration Scaffold Status (Non-Gating)
- Human calibration protocol scaffolding is allowed and encouraged now.
- Human calibration execution is **explicitly non-gating** until scheduled study windows.
- Missing human calibration runs must not block merge to `911Bench-Sim` or `911Bench`.

## Rollback Strategy
- If any gate fails materially, abandon `911Bench-Sim-S` branch work and continue from stable `911Bench-Sim`.
- If gates pass, mirror `911Bench-Sim-S` into `911Bench-Sim`, then into `911Bench`.

## Immediate Next Coding Task
- Implement Section 3.1 schema extension + minimal interruption/non-responsive behavior (Phase 1, Step 1) with deterministic seed and tests.
