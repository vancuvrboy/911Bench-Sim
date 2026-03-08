"""Role-based agent provider registry for deterministic/replay/OpenAI agents."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agents.caller_agent import CallerAgent
from agents.calltaker_agent import CTDecision, CallTakerAgent
from agents.qa_agent import QAEvaluatorAgent


@dataclass(frozen=True)
class AgentProfile:
    id: str
    role: str
    provider: str
    model: str
    temperature: float
    description: str
    mode: str


_CATALOG: list[AgentProfile] = [
    AgentProfile(
        id="manual",
        role="caller",
        provider="builtin",
        model="-",
        temperature=0.0,
        description="UI/manual caller turns only",
        mode="manual",
    ),
    AgentProfile(
        id="deterministic_v1",
        role="caller",
        provider="builtin",
        model="rule-based",
        temperature=0.3,
        description="Deterministic scripted caller",
        mode="callable",
    ),
    AgentProfile(
        id="replay",
        role="caller",
        provider="builtin",
        model="fixture-replay",
        temperature=0.0,
        description="Replay pre-recorded caller outputs",
        mode="replay",
    ),
    AgentProfile(
        id="openai_gpt4o_mini_v1",
        role="caller",
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.3,
        description="OpenAI caller adapter (Responses API)",
        mode="callable",
    ),
    AgentProfile(
        id="manual",
        role="calltaker",
        provider="builtin",
        model="-",
        temperature=0.0,
        description="UI/manual call-taker turns only",
        mode="manual",
    ),
    AgentProfile(
        id="deterministic_v1",
        role="calltaker",
        provider="builtin",
        model="rule-based",
        temperature=0.0,
        description="Deterministic scripted call-taker",
        mode="callable",
    ),
    AgentProfile(
        id="replay",
        role="calltaker",
        provider="builtin",
        model="fixture-replay",
        temperature=0.0,
        description="Replay pre-recorded call-taker outputs",
        mode="replay",
    ),
    AgentProfile(
        id="openai_gpt4o_mini_v1",
        role="calltaker",
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.0,
        description="OpenAI call-taker adapter (JSON action output)",
        mode="callable",
    ),
    AgentProfile(
        id="manual",
        role="qa",
        provider="builtin",
        model="-",
        temperature=0.0,
        description="No QA evaluator",
        mode="manual",
    ),
    AgentProfile(
        id="deterministic_v1",
        role="qa",
        provider="builtin",
        model="rule-based",
        temperature=0.0,
        description="Deterministic QA evaluator",
        mode="callable",
    ),
    AgentProfile(
        id="replay",
        role="qa",
        provider="builtin",
        model="fixture-replay",
        temperature=0.0,
        description="Replay QA score fixture if available",
        mode="replay",
    ),
    AgentProfile(
        id="openai_gpt4o_mini_v1",
        role="qa",
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.0,
        description="OpenAI QA adapter (JSON rubric scoring)",
        mode="callable",
    ),
]


def list_profiles() -> list[dict[str, Any]]:
    return [asdict(p) for p in _CATALOG]


def get_profile(role: str, agent_id: str) -> AgentProfile:
    for p in _CATALOG:
        if p.role == role and p.id == agent_id:
            return p
    raise ValueError(f"unknown agent profile: role={role}, id={agent_id}")


def is_replay(role: str, agent_id: str) -> bool:
    return get_profile(role, agent_id).mode == "replay"


def is_manual(role: str, agent_id: str) -> bool:
    return get_profile(role, agent_id).mode == "manual"


def create_caller_agent(agent_id: str, caller_json: dict[str, Any], incident_json: dict[str, Any]) -> CallerAgent | Any | None:
    profile = get_profile("caller", agent_id)
    if profile.mode in {"manual", "replay"}:
        return None
    if profile.provider == "builtin":
        return CallerAgent(caller_json=caller_json, incident_json=incident_json, temperature=profile.temperature)
    return _create_openai_caller(profile, caller_json, incident_json)


def create_calltaker_agent(agent_id: str, incident_json: dict[str, Any], **kwargs: Any) -> CallTakerAgent | Any | None:
    profile = get_profile("calltaker", agent_id)
    if profile.mode in {"manual", "replay"}:
        return None
    if profile.provider == "builtin":
        return CallTakerAgent(incident_json=incident_json, temperature=profile.temperature, **kwargs)
    return _create_openai_calltaker(profile, incident_json)


def create_qa_agent(agent_id: str, qa_template_json: dict[str, Any], **kwargs: Any) -> QAEvaluatorAgent | Any | None:
    profile = get_profile("qa", agent_id)
    if profile.mode in {"manual", "replay"}:
        return None
    if profile.provider == "builtin":
        return QAEvaluatorAgent(qa_template_json=qa_template_json, temperature=profile.temperature, **kwargs)
    return _create_openai_qa(profile, qa_template_json)


def _create_openai_client() -> Any:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("openai package not installed; install it to use OpenAI agent profiles") from exc
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _read_prompt_from_env() -> str:
    prompt_file = str(os.environ.get("OPENAI_CALLER_SYSTEM_PROMPT_FILE", "")).strip()
    if prompt_file:
        path = Path(prompt_file).expanduser()
        if path.exists():
            return path.read_text(encoding="utf-8")
    inline_prompt = str(os.environ.get("OPENAI_CALLER_SYSTEM_PROMPT", "")).strip()
    if inline_prompt:
        return inline_prompt
    return (
        "You are role-playing a 911 caller in a training simulator. "
        "Speak naturally as a stressed but cooperative caller. "
        "Only output the caller utterance text, no JSON, no labels, no analysis. "
        "Keep responses concise (1-3 sentences)."
    )


class OpenAICallerAgent:
    def __init__(self, model: str, temperature: float, caller_json: dict[str, Any], incident_json: dict[str, Any]) -> None:
        self.client = _create_openai_client()
        self.model = str(os.environ.get("OPENAI_CALLER_MODEL", model)).strip() or model
        self.temperature = float(os.environ.get("OPENAI_CALLER_TEMPERATURE", str(temperature)))
        self.caller_json = caller_json
        self.incident_json = incident_json
        self.system_prompt = _read_prompt_from_env()
        self._fallback = CallerAgent(caller_json=caller_json, incident_json=incident_json, temperature=temperature)

    def _user_prompt(self, call_taker_text: str, system_events: list[dict[str, Any]]) -> str:
        profile_id = str(self.caller_json.get("profile_id", "CALLER-UNKNOWN"))
        incident_type = str(self.incident_json.get("type", "Unknown"))
        opening = str((self.incident_json.get("caller_view", {}) or {}).get("initial_opening_line", "I need help."))
        return (
            f"caller_profile_id={profile_id}\n"
            f"incident_type={incident_type}\n"
            f"opening_line_hint={opening}\n"
            f"latest_call_taker_text={call_taker_text}\n"
            f"recent_system_events={json.dumps(system_events[-4:])}\n"
            "Generate the next caller utterance now."
        )

    def _extract_text(self, resp: Any) -> str:
        output_text = str(getattr(resp, "output_text", "") or "").strip()
        if output_text:
            return output_text
        output = getattr(resp, "output", None)
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    for part in content:
                        txt = str(getattr(part, "text", "") or "").strip()
                        if txt:
                            chunks.append(txt)
            joined = "\n".join(chunks).strip()
            if joined:
                return joined
        return ""

    def next_turn(self, call_taker_text: str, system_events: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        try:
            resp = self.client.responses.create(
                model=self.model,
                temperature=self.temperature,
                input=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self._user_prompt(call_taker_text, system_events)},
                ],
            )
            text = self._extract_text(resp)
            if not text:
                raise ValueError("empty_openai_responses_output")
            _, fallback_meta = self._fallback.next_turn(call_taker_text=call_taker_text, system_events=system_events)
            meta = dict(fallback_meta)
            meta.update(
                {
                    "model_provider": "openai",
                    "model": self.model,
                    "api": "responses",
                    "response_id": str(getattr(resp, "id", "")),
                }
            )
            return text, meta
        except Exception:
            return self._fallback.next_turn(call_taker_text=call_taker_text, system_events=system_events)


class OpenAICallTakerAgent:
    def __init__(self, model: str, temperature: float, incident_json: dict[str, Any]) -> None:
        self.client = _create_openai_client()
        self.model = model
        self.temperature = temperature
        self.incident_json = incident_json
        self._fallback = CallTakerAgent(incident_json=incident_json, temperature=temperature)

    def next_turn(self, caller_text: str, cad_state: dict[str, Any], system_events: list[dict[str, Any]]) -> CTDecision:
        try:
            prompt = (
                "You are a 911 call-taker. Return strict JSON with keys: "
                "text(str), cad_updates(object), end_call(bool), end_reason(str|null).\n"
                f"caller_text={caller_text}\n"
                f"cad_state={json.dumps(cad_state)}\n"
                f"system_events={json.dumps(system_events[-3:])}\n"
            )
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (resp.choices[0].message.content or "").strip()
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("invalid_openai_ct_payload")
            return CTDecision(
                text=str(obj.get("text", "")) or "Acknowledged.",
                cad_updates=obj.get("cad_updates") if isinstance(obj.get("cad_updates"), dict) else {},
                end_call=bool(obj.get("end_call", False)),
                end_reason=str(obj.get("end_reason")) if obj.get("end_reason") else None,
            )
        except Exception:
            return self._fallback.next_turn(caller_text=caller_text, cad_state=cad_state, system_events=system_events)


class OpenAIQAEvaluatorAgent:
    def __init__(self, model: str, temperature: float, qa_template_json: dict[str, Any]) -> None:
        self.client = _create_openai_client()
        self.model = model
        self.temperature = temperature
        self.qa_template_json = qa_template_json
        self._fallback = QAEvaluatorAgent(qa_template_json=qa_template_json, temperature=temperature)

    def evaluate(self, events: list[dict[str, Any]], incident_type: str) -> dict[str, Any]:
        try:
            prompt = (
                "Score this 911 transcript. Return strict JSON with fields matching deterministic QA output.\n"
                f"incident_type={incident_type}\n"
                f"events={json.dumps(events[-30:])}\n"
            )
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = (resp.choices[0].message.content or "").strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or "normalized_score" not in parsed:
                raise ValueError("invalid_openai_qa_payload")
            return parsed
        except Exception:
            return self._fallback.evaluate(events=events, incident_type=incident_type)


def _create_openai_caller(profile: AgentProfile, caller_json: dict[str, Any], incident_json: dict[str, Any]) -> OpenAICallerAgent:
    return OpenAICallerAgent(model=profile.model, temperature=profile.temperature, caller_json=caller_json, incident_json=incident_json)


def _create_openai_calltaker(profile: AgentProfile, incident_json: dict[str, Any]) -> OpenAICallTakerAgent:
    return OpenAICallTakerAgent(model=profile.model, temperature=profile.temperature, incident_json=incident_json)


def _create_openai_qa(profile: AgentProfile, qa_template_json: dict[str, Any]) -> OpenAIQAEvaluatorAgent:
    return OpenAIQAEvaluatorAgent(model=profile.model, temperature=profile.temperature, qa_template_json=qa_template_json)
