# SIM-GOV Correlation Contract (Draft)

Date: 2026-03-08  
Scope: Correlation and traceability contract for running 911Bench-Sim with Governance server.

## Purpose

Define stable correlation fields so SIM artifacts and Governance audit logs can be joined deterministically for analysis, debugging, and reproducibility.

## Canonical Correlation Fields

- `run_id`: batch/run grouping ID (many episodes).
- `scenario_id`: experiment/scenario label.
- `incident_id`: unique episode entity ID.
- `trace_id`: per action/proposal flow ID spanning northbound + southbound operations.
- `action_id`: proposal/action identifier (within an incident).
- `checkpoint_request_id`: checkpoint lifecycle identifier (when applicable).

## Generation and Ownership

- SIM owns generation of:
  - `run_id` (runtime startup or caller-supplied)
  - `scenario_id` (UI/script-supplied or auto-generated)
  - `incident_id` (from incident fixture / load routine)
- Governance owns generation of:
  - `trace_id` (if absent from incoming request)
  - governance-side request correlation IDs as needed
- If a field is already supplied by upstream, downstream must preserve it.

## Propagation Rules

1. At SIM episode start, SIM establishes `run_id`, `scenario_id`, `incident_id`.
2. On first governance interaction, SIM passes those fields in payload/context.
3. Governance includes `run_id`, `scenario_id`, `incident_id`, `trace_id`, `action_id` in:
   - request logs
   - decision/audit entries
   - southbound apply/checkpoint payloads
4. SIM records governance-emitted fields in `_events` system/correlation events.
5. Checkpoint flows additionally carry `checkpoint_request_id` and escalation depth.

## Event/Audit Requirements

Minimum field set for joinable records:

- SIM `_events` records related to governance:
  - `run_id`, `scenario_id`, `incident_id`, `trace_id`, `action_id`
- GOV audit rows:
  - `run_id`, `scenario_id`, `incident_id`, `trace_id`, `action_id`
- Checkpoint records on both sides:
  - `checkpoint_request_id`, `trace_id`, `incident_id`

## Artifact Cross-Link Requirements

- SIM episode `meta.json` should include:
  - governance audit bundle id/path reference (if known)
  - correlation summary (`run_id`, `scenario_id`, `incident_id`)
- Governance report/audit bundle should include:
  - SIM artifact root/path reference
  - same correlation summary

## Validation Checks (to add in integration harness)

1. Every governance decision has matching SIM correlation event (`trace_id` + `action_id`).
2. No orphan governance audit entries for a given `run_id/scenario_id/incident_id`.
3. Checkpoint request IDs match on both sides.
4. Correlation keys are present and non-empty in required record types.

## Versioning

- Contract version: `v0.1-draft`
- Backward-compatible additions allowed.
- Breaking field/name changes require explicit version bump and migration note.
