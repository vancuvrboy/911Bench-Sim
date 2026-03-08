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

## Section 2.6 Web Call Console UI

Run the thin backend + single-page console:

```bash
python3 -m sim_server.console_server --root . --host 127.0.0.1 --port 8101 --agent-config-dir agents/config
```

Open:

```text
http://127.0.0.1:8101
```

Episode setup includes selectable agent profiles for `caller`, `calltaker`, and `qa`.
The backend exposes `GET /api/agent/catalog`, and `POST /api/admin/load_start` accepts:
- `caller_agent_id`
- `calltaker_agent_id`
- `qa_agent_id`

Supported profile IDs include:
- `manual`
- `deterministic_v1`
- `replay`
- `openai_gpt4o_mini_v1` (requires `OPENAI_API_KEY` and `openai` package)

### OpenAI Caller (Responses API) quick setup

Use profile `openai_gpt4o_mini_v1` for `caller` and `manual` for `calltaker` in the web console.

Required:

```bash
export OPENAI_API_KEY="<your_key>"
```

Caller model/prompt settings are loaded from YAML config files at startup (one file per role+profile):

- `agents/config/caller.openai_gpt4o_mini_v1.yaml`
- `agents/config/calltaker.openai_gpt4o_mini_v1.yaml`
- `agents/config/qa.openai_gpt4o_mini_v1.yaml`

The caller adapter seeds full `caller.json` and `incident.json` into the conversation at episode start, then sends incremental turn updates each step using Responses API continuity (`previous_response_id`) when available. It falls back to deterministic caller behavior if generation fails.
