"""Standalone 911Bench SIM server core engine.

Implements Section 2 interfaces as in-process Python methods for harness-driven testing.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sim_server.errors import ConflictError, StateError, ValidationError
from sim_server.schema_utils import validate_event_minimal, validate_seed_triplet


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class CheckpointRequest:
    request_id: str
    incident_id: str
    action_class: str
    proposed_payload: dict[str, Any]
    evidence_summary: str
    approver_role: str
    source: str
    escalation_context: dict[str, Any] | None
    timeout_ms: int
    created_ts: str
    timeout_ts: str
    status: str = "pending"
    edited_payload: dict[str, Any] | None = None
    deferred_to: str | None = None
    rationale: str | None = None
    latency_ms: int | None = None


@dataclass
class Episode:
    incident_id: str
    scenario_id: str
    caller_json: dict[str, Any]
    incident_json: dict[str, Any]
    qa_template_id: str
    qa_template_json: dict[str, Any]
    phase: str = "loaded"
    start_ts: str | None = None
    end_ts: str | None = None
    current_turn: int = 0
    awaiting_caller_for_turn: int = 1
    pending_caller_text: str = ""
    pending_caller_metadata: dict[str, Any] | None = None
    agent_config_snapshot: dict[str, Any] | None = None
    dispatch_triggered: bool = False
    dispatch_turn: int | None = None
    post_dispatch_turn_count: int = 0
    responders_arrived: bool = False
    post_arrival_turn_count: int = 0
    max_turns: int = 30
    first_responder_delay: int = 8
    post_arrival_grace_turns: int = 2
    cad_state: dict[str, Any] = field(default_factory=dict)
    record_version: int = 0
    field_versions: dict[str, int] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    sealed_artifacts: dict[str, Any] = field(default_factory=dict)
    checkpoints: dict[str, CheckpointRequest] = field(default_factory=dict)
    degradation_cfg: dict[str, Any] = field(default_factory=dict)
    degradation_rng_seed: int = 0
    cumulative_stress_load: int = 0
    deferred_dispatch_turns: int = 0
    sim_time_ms: int = 0


class SimulationEngine:
    """In-process SIM engine exposing Section 2 plant/control and role tools."""

    def __init__(self, execution_id: str | None = None) -> None:
        self.execution_id = execution_id or f"exec-{uuid.uuid4().hex[:12]}"
        self._episodes: dict[str, Episode] = {}

    # ------------------------------------------------------------------
    # Harness/Admin interfaces
    # ------------------------------------------------------------------
    def admin_load_scenario(
        self,
        scenario_id: str,
        caller_json: dict[str, Any],
        incident_json: dict[str, Any],
        qa_template_id: str,
        qa_template_json: dict[str, Any],
        agent_config_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_seed_triplet(caller_json, incident_json, qa_template_json)

        incident_id = str(incident_json["id"])
        if incident_id in self._episodes:
            raise StateError("incident_exists", f"incident_id already loaded: {incident_id}")

        ep = Episode(
            incident_id=incident_id,
            scenario_id=scenario_id,
            caller_json=caller_json,
            incident_json=incident_json,
            qa_template_id=qa_template_id,
            qa_template_json=qa_template_json,
            agent_config_snapshot=self._normalize_agent_config_snapshot(agent_config_snapshot),
            first_responder_delay=int(incident_json.get("first_responder_delay", 8)),
            max_turns=int(incident_json.get("max_turns", 30)),
            degradation_cfg=self._normalize_degradation_config(
                incident_id=incident_id,
                caller_json=caller_json,
                config=incident_json.get("calltaker_degradation_config", {}),
            ),
        )
        ep.degradation_rng_seed = int(ep.degradation_cfg.get("degradation_seed", 0))
        self._episodes[incident_id] = ep
        return {"incident_id": incident_id, "status": "loaded"}

    def episode_start(self, incident_id: str) -> dict[str, Any]:
        ep = self._get_episode(incident_id)
        if ep.phase != "loaded":
            raise StateError("invalid_state", "episode already running or sealed")

        ep.phase = "running"
        ep.start_ts = _iso_now()
        self._append_event(
            ep,
            {
                "event_type": "meta",
                "execution_id": self.execution_id,
                "scenario_id": ep.scenario_id,
                "incident_id": ep.incident_id,
                "policy_id": "sim-standalone",
                "policy_hash": "sim-standalone",
                "helperFlag": False,
                "humanCTFlag": False,
                "humanCTName": None,
                "caller_profile_id": ep.caller_json.get("profile_id", "unknown"),
                "incident_type": ep.incident_json.get("type", "unknown"),
                "qa_template_id": ep.qa_template_id,
                "schema_version": "events.v4",
                "agent_config": self._normalize_agent_config_snapshot(ep.agent_config_snapshot),
                "stress_config": ep.caller_json.get("stressor_config", {}),
                "degradation_config": ep.degradation_cfg,
            },
        )
        return {"status": "running", "episode_ts": ep.start_ts}

    def episode_end(self, incident_id: str, reason: str, reason_detail: str | None = None) -> dict[str, Any]:
        ep = self._get_episode(incident_id)
        if ep.phase != "running":
            raise StateError("invalid_state", "episode not in running state")
        self._seal_episode(ep, reason=reason, reason_detail=reason_detail)
        return {
            "status": "sealed",
            "event_count": len(ep.events),
            "final_record_version": ep.record_version,
        }

    # ------------------------------------------------------------------
    # Role-client interfaces
    # ------------------------------------------------------------------
    def caller_post_turn(self, incident_id: str, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        ep = self._get_running_episode(incident_id)
        self._assert_not_sealed(ep)

        turn = ep.awaiting_caller_for_turn
        sanitized = self._sanitize_caller_metadata(metadata)
        existing_text = str(ep.pending_caller_text or "")
        if existing_text and self._is_interruption_followup(sanitized):
            ep.pending_caller_text = f"{existing_text}\n{text}".strip()
            ep.pending_caller_metadata = self._merge_caller_metadata(ep.pending_caller_metadata, sanitized)
        else:
            ep.pending_caller_text = text
            ep.pending_caller_metadata = sanitized

        return {"turn": turn, "ts": _iso_now(), "status": "accepted"}

    def calltaker_post_turn(
        self,
        incident_id: str,
        text: str,
        cad_updates: dict[str, Any] | None = None,
        call_taker_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ep = self._get_running_episode(incident_id)
        self._assert_not_sealed(ep)

        turn = ep.awaiting_caller_for_turn
        caller_text = ep.pending_caller_text
        caller_metadata = ep.pending_caller_metadata
        ct_metadata = self._sanitize_call_taker_metadata(call_taker_metadata)
        ep.pending_caller_text = ""
        ep.pending_caller_metadata = None

        adjusted_text, adjusted_updates, degradation_events = self._apply_degradation(
            ep=ep,
            turn=turn,
            text=text,
            cad_updates=cad_updates or {},
            caller_metadata=caller_metadata,
        )

        ep.current_turn = turn
        self._append_event(
            ep,
            {
                "event_type": "conversation",
                "incident_id": ep.incident_id,
                "turn": turn,
                "call_taker": adjusted_text,
                "caller": caller_text,
                "caller_metadata": caller_metadata,
                "call_taker_metadata": ct_metadata,
            },
        )
        if not str(caller_text or "").strip():
            self._append_system(ep, subtype="silent_turn", text="Caller provided no verbal content this turn.")
        if isinstance(caller_metadata, dict):
            markers = caller_metadata.get("stressor_markers")
            if isinstance(markers, list):
                stress_level = int(caller_metadata.get("stress_level", 0) or 0)
                stress_detail = caller_metadata.get("stressor_detail", {})
                for marker in markers:
                    self._append_event(
                        ep,
                        {
                            "event_type": "stressor_applied",
                            "incident_id": ep.incident_id,
                            "turn": turn,
                            "marker": str(marker),
                            "stress_level": stress_level,
                            "detail": stress_detail.get(str(marker)) if isinstance(stress_detail, dict) else None,
                        },
                    )
        for marker, detail in degradation_events:
            self._append_event(
                ep,
                {
                    "event_type": "degradation_applied",
                    "incident_id": ep.incident_id,
                    "turn": turn,
                    "marker": marker,
                    "detail": detail,
                },
            )
        ep.awaiting_caller_for_turn += 1

        cad_update_result = None
        if adjusted_updates:
            cad_update_result = self._apply_tool_call_update(ep, adjusted_updates)

        self._on_turn_progress(ep)
        return {
            "turn": turn,
            "ts": _iso_now(),
            "status": "accepted",
            "cad_update_result": cad_update_result,
        }

    def calltaker_end_call(
        self,
        incident_id: str,
        reason: str,
        reason_detail: str | None = None,
        human_override: bool = False,
    ) -> dict[str, Any]:
        ep = self._get_running_episode(incident_id)
        reason = str(reason or "").strip() or "other"
        automated_allowed_reasons = {"responders_arrived", "resolved_no_dispatch", "caller_disconnected", "prank_call", "other"}
        allowed_reasons = automated_allowed_reasons | {"terminated_by_human"} if human_override else automated_allowed_reasons
        if reason not in allowed_reasons:
            raise StateError(
                "invalid_end_reason",
                f"unsupported end reason: {reason}",
            )

        # Keep end-reason consistency checks active for all standard reasons.
        # "terminated_by_human" is the explicit manual override reason.
        if reason != "terminated_by_human":
            if ep.dispatch_triggered:
                if not ep.responders_arrived and reason != "responders_arrived":
                    raise StateError(
                        "invalid_end_reason",
                        "dispatch already triggered; cannot end call before responders_arrived",
                    )
            if reason == "responders_arrived" and not ep.responders_arrived:
                raise StateError("invalid_end_reason", "responders have not arrived yet")
            if reason == "resolved_no_dispatch" and ep.dispatch_triggered:
                raise StateError("invalid_end_reason", "dispatch already triggered; use responders_arrived path")
        if reason == "caller_disconnected":
            self._append_system(ep, subtype="call_dropped", text="Caller disconnected.")

        self._seal_episode(ep, reason=reason, reason_detail=reason_detail)
        return {
            "status": "ending",
            "episode_end_event_seq": ep.events[-1]["event_seq"],
        }

    # ------------------------------------------------------------------
    # Governance southbound interfaces
    # ------------------------------------------------------------------
    def plant_get_state_snapshot(self, incident_id: str) -> dict[str, Any]:
        ep = self._get_episode(incident_id)
        return {
            "cad_state": dict(ep.cad_state),
            "record_version": ep.record_version,
            "field_versions": dict(ep.field_versions),
            "location": {
                "address_line": ep.cad_state.get("location") or ep.incident_json.get("location", {}).get("address_line", ""),
                "city": ep.incident_json.get("location", {}).get("city", ""),
            },
            "episode_phase": ep.phase,
        }

    def plant_get_transcript_since(self, incident_id: str, cursor: int) -> dict[str, Any]:
        ep = self._get_episode(incident_id)
        turns: list[dict[str, Any]] = []
        for ev in ep.events:
            if ev.get("event_type") != "conversation":
                continue
            if int(ev.get("turn", 0)) > int(cursor):
                turns.append({"turn": ev["turn"], "call_taker": ev["call_taker"], "caller": ev["caller"], "ts": ev["ts"]})
        new_cursor = max((t["turn"] for t in turns), default=cursor)
        return {"turns": turns, "new_cursor": new_cursor}

    def checkpoint_request(self, incident_id: str, request: dict[str, Any]) -> dict[str, Any]:
        ep = self._get_running_episode(incident_id)
        self._assert_not_sealed(ep)

        source = request.get("source", "checkpoint")
        if source in {"escalation_reactive", "escalation_proactive"} and not request.get("escalation_context"):
            raise ValidationError("invalid_checkpoint_request", "escalation_context required for escalation source")

        timeout_ms = int(request.get("timeout_ms", 30000))
        created = _iso_now()
        timeout_ts = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(milliseconds=timeout_ms)).isoformat()
        req = CheckpointRequest(
            request_id=request.get("request_id") or f"req-{uuid.uuid4().hex[:10]}",
            incident_id=incident_id,
            action_class=request.get("action_class", "unknown"),
            proposed_payload=request.get("proposed_payload", {}),
            evidence_summary=request.get("evidence_summary", ""),
            approver_role=request.get("approver_role", "call_taker"),
            source=source,
            escalation_context=request.get("escalation_context"),
            timeout_ms=timeout_ms,
            created_ts=created,
            timeout_ts=timeout_ts,
        )
        ep.checkpoints[req.request_id] = req
        return {"request_id": req.request_id, "status": "pending"}

    def checkpoint_poll(self, request_id: str) -> dict[str, Any]:
        req, _ep = self._get_checkpoint(request_id)
        if req.status == "pending" and self._is_timed_out(req):
            req.status = "timeout"
            req.latency_ms = req.timeout_ms
            req.rationale = "timeout"
            self._append_checkpoint_decision(_ep, req)

        response: dict[str, Any] = {"latency_ms": int(req.latency_ms or 0)}
        if req.edited_payload is not None:
            response["edited_payload"] = req.edited_payload
        if req.deferred_to is not None:
            response["deferred_to"] = req.deferred_to
        if req.rationale is not None:
            response["rationale"] = req.rationale

        return {"status": req.status, "response": response}

    def checkpoint_list(
        self,
        incident_id: str,
        status_filter: str | None = "pending",
        role_filter: str | None = None,
    ) -> dict[str, Any]:
        ep = self._get_episode(incident_id)
        requests: list[dict[str, Any]] = []
        for req in ep.checkpoints.values():
            if status_filter and req.status != status_filter:
                continue
            if role_filter and req.approver_role != role_filter:
                continue
            requests.append(
                {
                    "request_id": req.request_id,
                    "action_class": req.action_class,
                    "proposed_payload": req.proposed_payload,
                    "evidence_summary": req.evidence_summary,
                    "source": req.source,
                    "escalation_context": req.escalation_context,
                    "created_ts": req.created_ts,
                    "timeout_ts": req.timeout_ts,
                    "approver_role": req.approver_role,
                    "status": req.status,
                }
            )
        return {"requests": requests}

    def checkpoint_submit(
        self,
        request_id: str,
        decision: str,
        edited_payload: dict[str, Any] | None = None,
        re_escalate_to: str | None = None,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        req, ep = self._get_checkpoint(request_id)
        if req.status != "pending":
            raise StateError("checkpoint_resolved", "request already resolved")

        now = dt.datetime.now(dt.timezone.utc)
        created = dt.datetime.fromisoformat(req.created_ts)
        req.latency_ms = int((now - created).total_seconds() * 1000)

        if decision == "approved":
            req.status = "approved"
        elif decision == "denied":
            req.status = "denied"
        elif decision == "edited_approved":
            if not edited_payload:
                raise ValidationError("invalid_decision", "edited_payload required for edited_approved")
            req.status = "edited_approved"
            req.edited_payload = edited_payload
        elif decision == "deferred_escalated":
            req.status = "deferred_escalated"
            req.deferred_to = "supervisor"
        elif decision == "re_escalated":
            req.status = "deferred_escalated"
            req.deferred_to = re_escalate_to or "supervisor"
        else:
            raise ValidationError("invalid_decision", f"unsupported checkpoint decision: {decision}")

        req.rationale = rationale
        self._append_checkpoint_decision(ep, req)

        new_request_id = None
        if decision in {"deferred_escalated", "re_escalated"}:
            esc_to = req.deferred_to or "supervisor"
            ctx = dict(req.escalation_context or {})
            ctx["escalation_depth"] = int(ctx.get("escalation_depth", 1)) + 1
            derived = CheckpointRequest(
                request_id=f"req-{uuid.uuid4().hex[:10]}",
                incident_id=req.incident_id,
                action_class=req.action_class,
                proposed_payload=req.proposed_payload,
                evidence_summary=req.evidence_summary,
                approver_role=esc_to,
                source="escalation_reactive",
                escalation_context=ctx,
                timeout_ms=req.timeout_ms,
                created_ts=_iso_now(),
                timeout_ts=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(milliseconds=req.timeout_ms)).isoformat(),
            )
            ep.checkpoints[derived.request_id] = derived
            new_request_id = derived.request_id

        return {"status": "recorded", "latency_ms": req.latency_ms, "new_request_id": new_request_id}

    def plant_apply_cad_patch(
        self,
        incident_id: str,
        action_id: str,
        action_class: str,
        payload: dict[str, Any],
        read_set: dict[str, Any],
        policy_id: str,
        policy_hash: str,
        proposer_agent_id: str,
        checkpoint_ref: str | None = None,
        checkpoint_decision: str | None = None,
        original_payload: dict[str, Any] | None = None,
        governance_operators_applied: list[str] | None = None,
    ) -> dict[str, Any]:
        ep = self._get_running_episode(incident_id)
        self._assert_not_sealed(ep)

        try:
            stale_fields = self._detect_stale_fields(ep, read_set)
            if stale_fields:
                current_versions = {k: ep.field_versions.get(k, 0) for k in stale_fields}
                return {
                    "status": "conflict",
                    "conflict_detail": {"stale_fields": stale_fields, "current_versions": current_versions},
                }

            old_values = {k: ep.cad_state.get(k) for k in payload}
            self._apply_patch(ep, payload)

            self._append_event(
                ep,
                {
                    "event_type": "cad_patch_applied",
                    "incident_id": ep.incident_id,
                    "turn": ep.current_turn,
                    "action_id": action_id,
                    "action_class": action_class,
                    "proposer_agent_id": proposer_agent_id,
                    "policy_id": policy_id,
                    "policy_hash": policy_hash,
                    "payload": payload,
                    "original_payload": original_payload or payload,
                    "checkpoint_ref": checkpoint_ref,
                    "checkpoint_decision": checkpoint_decision,
                    "governance_operators_applied": governance_operators_applied or [],
                    "old_values": old_values,
                    "new_record_version": ep.record_version,
                    "new_field_versions": {k: ep.field_versions[k] for k in payload.keys()},
                },
            )
            self._dispatch_detection_on_write(ep, payload)
            return {
                "status": "applied",
                "new_record_version": ep.record_version,
                "new_field_versions": {k: ep.field_versions[k] for k in payload.keys()},
            }
        except ConflictError as exc:
            return {"status": "conflict", "conflict_detail": exc.to_dict()}

    def plant_emit_event(self, event: dict[str, Any]) -> dict[str, Any]:
        incident_id = event.get("incident_id")
        if not incident_id:
            raise ValidationError("invalid_event", "incident_id required")
        ep = self._get_episode(incident_id)
        self._assert_not_sealed(ep)
        event_copy = dict(event)
        if "ts" not in event_copy:
            event_copy["ts"] = _iso_now()
        event_copy.setdefault("event_seq", 0)
        validate_event_minimal(event_copy)
        self._append_event(ep, event_copy)
        return {"status": "appended", "event_seq": event_copy["event_seq"]}

    # ------------------------------------------------------------------
    # Artifact interfaces
    # ------------------------------------------------------------------
    def artifact_get(self, incident_id: str, name: str) -> dict[str, Any]:
        ep = self._get_episode(incident_id)
        if ep.phase != "sealed":
            raise StateError("episode_not_sealed", "episode not yet sealed")
        if name not in ep.sealed_artifacts:
            raise ValidationError("artifact_not_found", f"unknown artifact: {name}")
        return {"name": name, "content": ep.sealed_artifacts[name]}

    def build_artifact_bundle(
        self,
        incident_id: str,
        *,
        qa_score: dict[str, Any] | None = None,
        qa_input: dict[str, Any] | None = None,
        qa_report_markdown: str | None = None,
        qa_report_html: str | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ep = self._get_episode(incident_id)
        if ep.phase != "sealed":
            raise StateError("episode_not_sealed", "episode not yet sealed")

        transcript_rows = [ev for ev in ep.events if ev.get("event_type") == "conversation"]
        events_ndjson = "\n".join(json.dumps(ev, sort_keys=True) for ev in ep.events)

        def _hash_obj(obj: Any) -> str:
            blob = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return hashlib.sha256(blob).hexdigest()

        meta: dict[str, Any] = {
            "execution_id": self.execution_id,
            "scenario_id": ep.scenario_id,
            "incident_id": ep.incident_id,
            "phase": ep.phase,
            "start_ts": ep.start_ts,
            "end_ts": ep.end_ts,
            "total_events": len(ep.events),
            "total_turns": int(ep.current_turn),
            "record_version": int(ep.record_version),
            "field_versions": dict(ep.field_versions),
            "fixtures": {
                "caller_profile_id": ep.caller_json.get("profile_id"),
                "incident_type": ep.incident_json.get("type"),
                "qa_template_id": ep.qa_template_id,
            },
            "seed_hashes": {
                "caller_json_sha256": _hash_obj(ep.caller_json),
                "incident_json_sha256": _hash_obj(ep.incident_json),
                "qa_template_json_sha256": _hash_obj(ep.qa_template_json),
            },
            "artifact_hashes": {
                "_events.ndjson.sha256": hashlib.sha256(events_ndjson.encode("utf-8")).hexdigest(),
                "transcript.json.sha256": _hash_obj(transcript_rows),
            },
        }
        if qa_score is not None:
            meta["artifact_hashes"]["qa_score.json.sha256"] = _hash_obj(qa_score)
            if isinstance(qa_score, dict):
                meta["qa_summary"] = {
                    "normalized_score": qa_score.get("normalized_score"),
                    "incident_type": qa_score.get("incident_type"),
                }
        if qa_input is not None:
            meta["artifact_hashes"]["qa_input.json.sha256"] = _hash_obj(qa_input)
        if qa_report_markdown is not None:
            meta["artifact_hashes"]["qa_report.md.sha256"] = hashlib.sha256(qa_report_markdown.encode("utf-8")).hexdigest()
        if qa_report_html is not None:
            meta["artifact_hashes"]["qa_report.html.sha256"] = hashlib.sha256(qa_report_html.encode("utf-8")).hexdigest()
        if extra_meta:
            meta.update(extra_meta)

        out: dict[str, Any] = {
            "_events.ndjson": events_ndjson,
            "transcript.json": transcript_rows,
            "meta.json": meta,
        }
        if qa_score is not None:
            out["qa_score.json"] = qa_score
        if qa_input is not None:
            out["qa_input.json"] = qa_input
        if qa_report_markdown is not None:
            out["qa_report.md"] = qa_report_markdown
        if qa_report_html is not None:
            out["qa_report.html"] = qa_report_html
        return out

    def save_artifact_bundle(
        self,
        incident_id: str,
        *,
        output_root: str | Path,
        run_id: str,
        episode_id: str | None = None,
        qa_score: dict[str, Any] | None = None,
        qa_input: dict[str, Any] | None = None,
        qa_report_markdown: str | None = None,
        qa_report_html: str | None = None,
        extra_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bundle = self.build_artifact_bundle(
            incident_id,
            qa_score=qa_score,
            qa_input=qa_input,
            qa_report_markdown=qa_report_markdown,
            qa_report_html=qa_report_html,
            extra_meta=extra_meta,
        )
        ep = self._get_episode(incident_id)

        def _slug(value: str) -> str:
            out = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value))
            return out.strip("_") or "unknown"

        scenario_slug = _slug(ep.scenario_id)
        incident_slug = _slug(ep.incident_id)
        if episode_id is None:
            end_stamp = (
                str(ep.end_ts or _iso_now())
                .replace(":", "")
                .replace("-", "")
                .replace(".", "")
                .replace("+0000", "Z")
                .replace("+00:00", "Z")
            )
            episode_id = f"{incident_slug}__{end_stamp}"

        run_root = Path(output_root) / _slug(run_id)
        episode_dir = run_root / scenario_slug / _slug(episode_id)
        episode_dir.mkdir(parents=True, exist_ok=True)

        for name, content in bundle.items():
            path = episode_dir / name
            if name.endswith(".ndjson") and isinstance(content, str):
                path.write_text(content + ("\n" if content and not content.endswith("\n") else ""), encoding="utf-8")
            elif name.endswith(".json"):
                path.write_text(json.dumps(content, indent=2, sort_keys=True), encoding="utf-8")
            else:
                path.write_text(str(content), encoding="utf-8")

        return {
            "run_id": run_id,
            "scenario_id": ep.scenario_id,
            "incident_id": ep.incident_id,
            "episode_id": episode_id,
            "episode_dir": str(episode_dir),
            "files": sorted(bundle.keys()),
        }

    def episode_events(self, incident_id: str) -> list[dict[str, Any]]:
        """Expose a copy of in-memory events for local harness orchestration."""
        ep = self._get_episode(incident_id)
        return json.loads(json.dumps(ep.events))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _seal_episode(self, ep: Episode, reason: str, reason_detail: str | None = None) -> None:
        if ep.phase == "sealed":
            return

        for req in ep.checkpoints.values():
            if req.status == "pending":
                req.status = "timeout"
                req.latency_ms = req.timeout_ms
                req.rationale = "timeout_on_seal"
                self._append_checkpoint_decision(ep, req)

        ep.end_ts = _iso_now()
        duration_ms = 0
        if ep.start_ts:
            start = dt.datetime.fromisoformat(ep.start_ts)
            end = dt.datetime.fromisoformat(ep.end_ts)
            duration_ms = int((end - start).total_seconds() * 1000)

        self._append_event(
            ep,
            {
                "event_type": "episode_end",
                "incident_id": ep.incident_id,
                "reason": reason,
                "reason_detail": reason_detail,
                "total_turns": ep.current_turn,
                "total_events": len(ep.events) + 1,
                "final_record_version": ep.record_version,
                "final_cad_state": dict(ep.cad_state),
                "duration_ms": duration_ms,
            },
        )

        ep.phase = "sealed"
        ep.sealed_artifacts["_events.ndjson"] = "\n".join(json.dumps(ev, sort_keys=True) for ev in ep.events)
        transcript_rows = [ev for ev in ep.events if ev.get("event_type") == "conversation"]
        ep.sealed_artifacts["transcript.json"] = transcript_rows

    def _append_checkpoint_decision(self, ep: Episode, req: CheckpointRequest) -> None:
        self._append_event(
            ep,
            {
                "event_type": "checkpoint_decision",
                "incident_id": ep.incident_id,
                "turn": ep.current_turn,
                "request_id": req.request_id,
                "action_class": req.action_class,
                "decision": req.status,
                "approver_role": req.approver_role,
                "edited_payload": req.edited_payload,
                "deferred_to": req.deferred_to,
                "rationale": req.rationale,
                "latency_ms": int(req.latency_ms or 0),
            },
        )

    def _apply_tool_call_update(self, ep: Episode, cad_updates: dict[str, Any]) -> dict[str, Any]:
        old_dispatch = bool(ep.cad_state.get("dispatch_triggered", False))
        self._apply_patch(ep, cad_updates)
        fields_updated = sorted(cad_updates.keys())
        self._append_event(
            ep,
            {
                "event_type": "tool_call",
                "incident_id": ep.incident_id,
                "turn": ep.current_turn,
                "tool_call_id": f"tool-{uuid.uuid4().hex[:10]}",
                "tool_name": "calltaker.post_turn.cad_updates",
                "args": {"cad_updates": cad_updates},
                "fields_updated": fields_updated,
                "field_count": len(fields_updated),
                "dispatch_triggered": bool(cad_updates.get("dispatch_triggered")) if "dispatch_triggered" in cad_updates else None,
                "actor": "call_taker",
                "new_record_version": ep.record_version,
                "new_field_versions": {k: ep.field_versions[k] for k in fields_updated},
            },
        )
        if not old_dispatch and bool(ep.cad_state.get("dispatch_triggered", False)):
            self._dispatch_detection_on_write(ep, cad_updates)
        return {
            "fields_updated": fields_updated,
            "new_record_version": ep.record_version,
        }

    def _apply_patch(self, ep: Episode, payload: dict[str, Any]) -> None:
        for key, value in payload.items():
            if key == "remarks_notes":
                old = str(ep.cad_state.get("remarks_notes", ""))
                ep.cad_state[key] = f"{old}\n{value}".strip() if old else value
            else:
                ep.cad_state[key] = value
            ep.field_versions[key] = ep.field_versions.get(key, 0) + 1
        ep.record_version += 1

    def _detect_stale_fields(self, ep: Episode, read_set: dict[str, Any]) -> list[str]:
        stale: list[str] = []
        read_record_version = int(read_set.get("record_version", 0))
        read_field_versions = read_set.get("field_versions", {}) or {}

        if read_record_version < ep.record_version:
            stale.extend(list(read_field_versions.keys()) or ["record_version"])

        for field, read_v in read_field_versions.items():
            current_v = ep.field_versions.get(field, 0)
            if int(read_v) < int(current_v):
                stale.append(field)

        # No silent merge: if record is stale and caller omitted fields, still conflict.
        if read_record_version < ep.record_version and not read_field_versions:
            stale.append("record_version")

        return sorted(set(stale))

    def _dispatch_detection_on_write(self, ep: Episode, payload: dict[str, Any]) -> None:
        dispatch_now = bool(payload.get("dispatch_triggered", ep.cad_state.get("dispatch_triggered", False)))
        if not ep.dispatch_triggered and dispatch_now:
            ep.dispatch_triggered = True
            ep.dispatch_turn = ep.current_turn
            self._append_system(
                ep,
                subtype="responders_dispatched",
                text="Responders dispatched.",
                detail={"dispatch_turn": ep.dispatch_turn},
            )

    def _on_turn_progress(self, ep: Episode) -> None:
        if ep.deferred_dispatch_turns > 0:
            ep.deferred_dispatch_turns -= 1
            if ep.deferred_dispatch_turns == 0 and not ep.dispatch_triggered:
                self._apply_patch(ep, {"dispatch_triggered": True})
                self._dispatch_detection_on_write(ep, {"dispatch_triggered": True})
                self._append_event(
                    ep,
                    {
                        "event_type": "degradation_applied",
                        "incident_id": ep.incident_id,
                        "turn": ep.current_turn,
                        "marker": "dispatch_delay_released",
                        "detail": {"dispatch_triggered": True},
                    },
                )

        if ep.current_turn >= ep.max_turns:
            self._append_system(ep, subtype="max_turns_reached", text="Maximum turns reached.")
            self._seal_episode(ep, reason="max_turns")
            return

        if ep.dispatch_triggered and not ep.responders_arrived:
            ep.post_dispatch_turn_count += 1
            if ep.post_dispatch_turn_count >= ep.first_responder_delay:
                ep.responders_arrived = True
                ep.post_arrival_turn_count = 0
                self._append_system(ep, subtype="responders_arrived", text="First responders have arrived.")
                return

        if ep.responders_arrived:
            ep.post_arrival_turn_count += 1
            if ep.post_arrival_turn_count >= ep.post_arrival_grace_turns:
                self._seal_episode(ep, reason="auto_end_post_arrival")

    def _append_system(self, ep: Episode, subtype: str, text: str, detail: dict[str, Any] | None = None) -> None:
        self._append_event(
            ep,
            {
                "event_type": "system",
                "incident_id": ep.incident_id,
                "turn": ep.current_turn,
                "subtype": subtype,
                "text": text,
                "detail": detail,
            },
        )

    def _append_event(self, ep: Episode, event: dict[str, Any]) -> None:
        if ep.phase == "sealed":
            raise StateError("episode_sealed", "episode is sealed")
        ev = dict(event)
        ev.setdefault("ts", _iso_now())
        ev["event_seq"] = len(ep.events)
        validate_event_minimal(ev)
        ep.events.append(ev)

    def _sanitize_caller_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(metadata, dict):
            return None
        allowed_keys = {
            "agent_profile_id",
            "source",
            "response_id",
            "fallback",
            "error_code",
            "stress_level",
            "stressor_markers",
            "stressor_detail",
            "emotional_state",
            "disclosure_tracker",
            "progression_note",
        }
        cleaned = {k: metadata[k] for k in allowed_keys if k in metadata}
        if not cleaned:
            return None
        if "fallback" in cleaned:
            cleaned["fallback"] = bool(cleaned["fallback"])
        if "stress_level" in cleaned:
            cleaned["stress_level"] = max(0, min(5, int(cleaned["stress_level"])))
        if "stressor_markers" in cleaned and isinstance(cleaned["stressor_markers"], list):
            cleaned["stressor_markers"] = [str(item) for item in cleaned["stressor_markers"]]
        return cleaned

    def _merge_caller_metadata(
        self,
        base: dict[str, Any] | None,
        extra: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(base, dict):
            return extra
        if not isinstance(extra, dict):
            return base
        out = dict(base)
        for key, value in extra.items():
            if key == "stressor_markers":
                merged = list(out.get(key, [])) if isinstance(out.get(key), list) else []
                if isinstance(value, list):
                    for marker in value:
                        marker_s = str(marker)
                        if marker_s not in merged:
                            merged.append(marker_s)
                out[key] = merged
                continue
            if key == "stressor_detail" and isinstance(value, dict):
                detail = dict(out.get(key, {})) if isinstance(out.get(key), dict) else {}
                detail.update(value)
                out[key] = detail
                continue
            out[key] = value
        return out

    def _is_interruption_followup(self, metadata: dict[str, Any] | None) -> bool:
        if not isinstance(metadata, dict):
            return False
        markers = metadata.get("stressor_markers")
        if not isinstance(markers, list):
            return False
        marker_set = {str(m) for m in markers}
        return "interruption" in marker_set

    def _sanitize_call_taker_metadata(self, metadata: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(metadata, dict):
            return None
        allowed_keys = {"agent_profile_id", "source", "response_id", "fallback", "fallback_reason", "error_code"}
        cleaned = {k: metadata[k] for k in allowed_keys if k in metadata}
        if not cleaned:
            return None
        if "fallback" in cleaned:
            cleaned["fallback"] = bool(cleaned["fallback"])
        return cleaned

    def _normalize_agent_config_snapshot(self, snapshot: dict[str, Any] | None) -> dict[str, Any]:
        default = {
            "caller_agent": {
                "profile_id": "unknown",
                "provider": "unknown",
                "mode": "unknown",
                "model": "unknown",
                "temperature": 0.0,
                "prompt_hash": "none",
            },
            "calltaker_agent": {
                "profile_id": "unknown",
                "provider": "unknown",
                "mode": "unknown",
                "model": "unknown",
                "temperature": 0.0,
                "prompt_hash": "none",
            },
            "helper_agent": None,
            "qa_agent": {
                "profile_id": "unknown",
                "provider": "unknown",
                "mode": "unknown",
                "model": "unknown",
                "temperature": 0.0,
                "prompt_hash": "none",
            },
        }
        if not isinstance(snapshot, dict):
            return default
        out = dict(default)
        for key in ("caller_agent", "calltaker_agent", "qa_agent"):
            value = snapshot.get(key)
            if isinstance(value, dict):
                merged = dict(out[key])
                merged.update({k: v for k, v in value.items() if k in merged or k == "config_sha256"})
                out[key] = merged
        helper = snapshot.get("helper_agent")
        out["helper_agent"] = helper if isinstance(helper, dict) else None
        return out

    def _normalize_degradation_config(self, *, incident_id: str, caller_json: dict[str, Any], config: Any) -> dict[str, Any]:
        cfg = config if isinstance(config, dict) else {}
        caller_stress = int((caller_json.get("stressor_config", {}) or {}).get("stress_level", 0) or 0)
        seed_material = f"{incident_id}:degradation"
        default_seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:8], 16)
        return {
            "enabled": bool(cfg.get("enabled", False)),
            "stress_level": max(0, min(5, int(cfg.get("stress_level", caller_stress) or caller_stress))),
            "degradation_seed": int(cfg.get("degradation_seed", default_seed) or default_seed),
            "omission_probability": max(0.0, min(1.0, float(cfg.get("omission_probability", 0.0)))),
            "verification_skip_probability": max(0.0, min(1.0, float(cfg.get("verification_skip_probability", 0.0)))),
            "dispatch_delay_probability": max(0.0, min(1.0, float(cfg.get("dispatch_delay_probability", 0.0)))),
            "dispatch_delay_turns": max(1, int(cfg.get("dispatch_delay_turns", 1))),
            "load_threshold": max(1, int(cfg.get("load_threshold", 4))),
            "turn_time_budget_ms": max(0, int(cfg.get("turn_time_budget_ms", 0))),
            "base_turn_cost_ms": max(0, int(cfg.get("base_turn_cost_ms", 2500))),
            "cad_field_cost_ms": max(0, int(cfg.get("cad_field_cost_ms", 900))),
            "interruption_penalty_ms": max(0, int(cfg.get("interruption_penalty_ms", 1200))),
            "nonresponsive_penalty_ms": max(0, int(cfg.get("nonresponsive_penalty_ms", 1500))),
            "load_increments": {
                "interruption": int(cfg.get("load_increments", {}).get("interruption", 1))
                if isinstance(cfg.get("load_increments"), dict)
                else 1,
                "non_responsive": int(cfg.get("load_increments", {}).get("non_responsive", 1))
                if isinstance(cfg.get("load_increments"), dict)
                else 1,
                "topic_digression": int(cfg.get("load_increments", {}).get("topic_digression", 1))
                if isinstance(cfg.get("load_increments"), dict)
                else 1,
                "contradiction": int(cfg.get("load_increments", {}).get("contradiction", 2))
                if isinstance(cfg.get("load_increments"), dict)
                else 2,
            },
        }

    def _apply_degradation(
        self,
        *,
        ep: Episode,
        turn: int,
        text: str,
        cad_updates: dict[str, Any],
        caller_metadata: dict[str, Any] | None,
    ) -> tuple[str, dict[str, Any], list[tuple[str, dict[str, Any]]]]:
        cfg = ep.degradation_cfg or {}
        if not bool(cfg.get("enabled", False)):
            return text, cad_updates, []

        rng = random.Random(ep.degradation_rng_seed + turn)
        markers: list[tuple[str, dict[str, Any]]] = []
        out_updates = dict(cad_updates)
        out_text = str(text)

        load_increments = cfg.get("load_increments", {}) if isinstance(cfg.get("load_increments"), dict) else {}
        if isinstance(caller_metadata, dict):
            for marker in caller_metadata.get("stressor_markers", []) or []:
                ep.cumulative_stress_load += int(load_increments.get(str(marker), 0))

        threshold = int(cfg.get("load_threshold", 4))
        multiplier = 1.0 if ep.cumulative_stress_load < threshold else 1.5

        markers_present = set()
        if isinstance(caller_metadata, dict):
            raw = caller_metadata.get("stressor_markers")
            if isinstance(raw, list):
                markers_present = {str(x) for x in raw}
        turn_budget_ms = int(cfg.get("turn_time_budget_ms", 0))
        if turn_budget_ms > 0:
            base_cost = int(cfg.get("base_turn_cost_ms", 2500))
            cad_cost = int(cfg.get("cad_field_cost_ms", 900)) * len(out_updates)
            int_penalty = int(cfg.get("interruption_penalty_ms", 1200)) * (1 if "interruption" in markers_present else 0)
            nonresp_penalty = int(cfg.get("nonresponsive_penalty_ms", 1500)) * (1 if "non_responsive" in markers_present else 0)
            estimated_ms = base_cost + cad_cost + int_penalty + nonresp_penalty
            ep.sim_time_ms += estimated_ms
            if estimated_ms > turn_budget_ms:
                markers.append(
                    (
                        "time_pressure",
                        {
                            "estimated_turn_cost_ms": estimated_ms,
                            "turn_budget_ms": turn_budget_ms,
                            "cad_field_count": len(out_updates),
                        },
                    )
                )
                # Under time pressure, raise degradation likelihood.
                multiplier *= 1.35

        om_prob = min(1.0, float(cfg.get("omission_probability", 0.0)) * multiplier)
        if out_updates and rng.random() < om_prob:
            keys = sorted(k for k in out_updates.keys() if k != "dispatch_triggered")
            if not keys:
                keys = sorted(out_updates.keys())
            dropped = keys[0] if keys else None
            if dropped is not None:
                out_updates.pop(dropped, None)
                markers.append(("omission_injected", {"dropped_field": dropped, "stress_load": ep.cumulative_stress_load}))

        ver_prob = min(1.0, float(cfg.get("verification_skip_probability", 0.0)) * multiplier)
        if rng.random() < ver_prob:
            markers.append(("verification_skipped", {"stress_load": ep.cumulative_stress_load}))

        delay_prob = min(1.0, float(cfg.get("dispatch_delay_probability", 0.0)) * multiplier)
        if bool(out_updates.get("dispatch_triggered")) and rng.random() < delay_prob:
            out_updates["dispatch_triggered"] = False
            # +1 because _on_turn_progress runs at the end of the current turn.
            ep.deferred_dispatch_turns = int(cfg.get("dispatch_delay_turns", 1)) + 1
            markers.append(
                (
                    "dispatch_delay_injected",
                    {"delay_turns": int(cfg.get("dispatch_delay_turns", 1)), "stress_load": ep.cumulative_stress_load},
                )
            )

        if markers and len(out_text.strip()) > 0 and rng.random() < 0.15:
            out_text = f"{out_text} Let me quickly verify that."
            markers.append(("question_order_perturbed", {"mode": "suffix_rephrase"}))

        return out_text, out_updates, markers

    def _is_timed_out(self, req: CheckpointRequest) -> bool:
        now = dt.datetime.now(dt.timezone.utc)
        timeout = dt.datetime.fromisoformat(req.timeout_ts)
        return now >= timeout

    def _assert_not_sealed(self, ep: Episode) -> None:
        if ep.phase == "sealed":
            raise StateError("episode_sealed", "episode is sealed")

    def _get_episode(self, incident_id: str) -> Episode:
        if incident_id not in self._episodes:
            raise StateError("incident_not_found", f"incident_id not found: {incident_id}")
        return self._episodes[incident_id]

    def _get_running_episode(self, incident_id: str) -> Episode:
        ep = self._get_episode(incident_id)
        if ep.phase == "sealed":
            raise StateError("episode_sealed", "episode is sealed")
        if ep.phase != "running":
            raise StateError("invalid_state", "episode not in running state")
        return ep

    def _get_checkpoint(self, request_id: str) -> tuple[CheckpointRequest, Episode]:
        for ep in self._episodes.values():
            if request_id in ep.checkpoints:
                return ep.checkpoints[request_id], ep
        raise StateError("checkpoint_not_found", f"request not found: {request_id}")
