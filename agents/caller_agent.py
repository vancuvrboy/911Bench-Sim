"""Deterministic caller agent for SIM Phase 1 integration."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any


DISCLOSURE_FIELDS = {
    "name": ("name",),
    "callback_number": ("phone", "number", "callback"),
    "current_location": ("where", "address", "location"),
    "relationship_to_incident": ("relationship",),
    "people_involved": ("who", "people"),
    "hazards_or_weapons": ("weapon", "hazard"),
}


@dataclass
class CallerState:
    turn: int = 0
    disclosed: dict[str, bool] = field(default_factory=dict)
    emotional_state: str = "concerned"
    contradiction_emitted: dict[str, bool] = field(default_factory=dict)


class CallerAgent:
    def __init__(self, caller_json: dict[str, Any], incident_json: dict[str, Any], temperature: float = 0.3) -> None:
        self.caller = caller_json
        self.incident = incident_json
        self.temperature = temperature
        self.state = CallerState(disclosed={k: False for k in DISCLOSURE_FIELDS})
        self.profile_id = str(caller_json.get("profile_id", "CALLER-UNKNOWN"))
        self._opening = str(incident_json.get("caller_view", {}).get("initial_opening_line", "I need help."))
        self._progression = {
            int(item.get("turn_offset", -1)): str(item.get("note", ""))
            for item in incident_json.get("progression_by_turn", [])
            if isinstance(item, dict)
        }
        self._stress_cfg = self._parse_stressor_config(caller_json.get("stressor_config"))
        seed_value = int(self._stress_cfg.get("seed", 0))
        self._rng = random.Random(seed_value)

    def next_turn(self, call_taker_text: str, system_events: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        self.state.turn += 1
        low = call_taker_text.lower()
        stress_markers: list[str] = []
        stress_detail: dict[str, Any] = {}

        # System-event-aware closing behavior.
        if any(ev.get("subtype") == "responders_arrived" for ev in system_events):
            self.state.emotional_state = "relieved"
            text = "Okay, I can see responders now. Thank you."
            return text, self._metadata(progression_note=None, stress_markers=[], stress_detail={})

        if self.state.turn == 1:
            text = self._opening
            text = self._apply_stress_behaviors(
                text=text,
                stress_markers=stress_markers,
                stress_detail=stress_detail,
                call_taker_text=call_taker_text,
            )
            return text, self._metadata(
                progression_note=self._progression.get(0),
                stress_markers=stress_markers,
                stress_detail=stress_detail,
            )

        emitted: list[str] = []
        for field, triggers in DISCLOSURE_FIELDS.items():
            policy = str((self.caller.get("disclosure_policy", {}) or {}).get(field, "on_ask_once"))
            asked = any(token in low for token in triggers)
            if self.state.disclosed.get(field):
                continue
            if policy == "volunteer" and self.state.turn <= 2:
                emitted.append(self._value_for(field))
                self.state.disclosed[field] = True
            elif policy == "on_ask_once" and asked:
                emitted.append(self._value_for(field))
                self.state.disclosed[field] = True
            elif policy == "on_ask_twice" and asked:
                key = f"ask_count_{field}"
                count = int(self.state.disclosed.get(key, 0)) + 1
                self.state.disclosed[key] = count
                if count >= 2:
                    emitted.append(self._value_for(field))
                    self.state.disclosed[field] = True
            elif policy == "after_reassurance" and asked and any(word in low for word in ("safe", "okay", "help is on the way")):
                emitted.append(self._value_for(field))
                self.state.disclosed[field] = True

        progression_note = self._progression.get(self.state.turn)
        if progression_note:
            emitted.append(progression_note)

        if not emitted:
            emitted.append("I understand. I am staying on the line.")

        disfluencies = ((self.caller.get("speech", {}) or {}).get("disfluencies") or [])
        if disfluencies and self.state.turn % 2 == 0:
            emitted.insert(0, str(disfluencies[0]))

        text = " ".join(emitted)
        text = self._apply_stress_behaviors(
            text=text,
            stress_markers=stress_markers,
            stress_detail=stress_detail,
            call_taker_text=call_taker_text,
        )
        return text, self._metadata(
            progression_note=progression_note,
            stress_markers=stress_markers,
            stress_detail=stress_detail,
        )

    def _value_for(self, field: str) -> str:
        identity = self.caller.get("identity", {}) or {}
        loc = self.incident.get("location", {}) or {}
        samples = self.caller.get("example_short_answers", {}) or {}
        if field == "name":
            return f"My name is {identity.get('name', samples.get('name', 'unknown'))}."
        if field == "callback_number":
            return f"My callback is {identity.get('phone_number', samples.get('callback_number', 'unknown'))}."
        if field == "current_location":
            return f"I am at {loc.get('address_line', 'the reported location')}."
        if field == "relationship_to_incident":
            return str(samples.get("relationship_to_incident", "I am nearby."))
        if field == "people_involved":
            return str(samples.get("people_involved", "I can see two people."))
        if field == "hazards_or_weapons":
            return "I do not see weapons, but there is a hazard."
        return ""

    def _metadata(self, progression_note: str | None, stress_markers: list[str], stress_detail: dict[str, Any]) -> dict[str, Any]:
        out = {
            "emotional_state": self.state.emotional_state,
            "disclosure_tracker": {k: bool(v) for k, v in self.state.disclosed.items() if not k.startswith("ask_count_")},
            "progression_note": progression_note,
            "stress_level": int(self._stress_cfg["stress_level"]),
        }
        if stress_markers:
            out["stressor_markers"] = list(stress_markers)
            out["stressor_detail"] = dict(stress_detail)
        return out

    def _parse_stressor_config(self, value: Any) -> dict[str, Any]:
        cfg = value if isinstance(value, dict) else {}
        stress_level = int(cfg.get("stress_level", 0) or 0)
        stress_level = max(0, min(5, stress_level))
        seed_material = f"{self.profile_id}:{self.incident.get('id', 'INC-UNKNOWN')}"
        default_seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:8], 16)
        interruption_default = bool(((self.caller.get("interaction_style") or {}).get("interrupts_operator")) or stress_level >= 2)
        return {
            "stress_level": stress_level,
            "seed": int(cfg.get("seed", default_seed) or default_seed),
            "interruption_policy": self._policy_defaults(
                cfg.get("interruption_policy"),
                enabled=interruption_default,
                probability=min(0.15 + (0.08 * stress_level), 0.9),
                marker="interruption",
            ),
            "non_responsive_policy": self._policy_defaults(
                cfg.get("non_responsive_policy"),
                enabled=stress_level >= 3,
                probability=min(0.05 + (0.07 * stress_level), 0.75),
                marker="non_responsive",
                extra={"mode": "silent", "non_verbal_text": "..."},
            ),
            "contradiction_policy": self._policy_defaults(
                cfg.get("contradiction_policy"),
                enabled=stress_level >= 3,
                probability=min(0.02 + (0.05 * stress_level), 0.6),
                marker="contradiction",
                extra={"field": "current_location", "text": "Wait, I might have the address wrong."},
            ),
            "topic_digression_policy": self._policy_defaults(
                cfg.get("topic_digression_policy"),
                enabled=stress_level >= 2,
                probability=min(0.08 + (0.05 * stress_level), 0.7),
                marker="topic_digression",
                extra={"text": "Please hurry, I am really scared right now."},
            ),
            "media_policy": cfg.get("media_policy", {}),
            "threat_escalation_policy": cfg.get("threat_escalation_policy", {}),
            "language_switching_policy": cfg.get("language_switching_policy", {}),
        }

    def _policy_defaults(
        self,
        policy: Any,
        *,
        enabled: bool,
        probability: float,
        marker: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        p = policy if isinstance(policy, dict) else {}
        out: dict[str, Any] = {
            "enabled": bool(p.get("enabled", enabled)),
            "turn_offsets": [int(t) for t in p.get("turn_offsets", []) if isinstance(t, int) or (isinstance(t, str) and t.isdigit())],
            "probability": float(p.get("probability", probability)),
            "marker": marker,
        }
        if extra:
            out.update(extra)
        out.update(p)
        out["enabled"] = bool(out.get("enabled"))
        out["turn_offsets"] = [int(t) for t in out.get("turn_offsets", []) if isinstance(t, int) or (isinstance(t, str) and t.isdigit())]
        out["probability"] = max(0.0, min(1.0, float(out["probability"])))
        return out

    def _policy_triggers(self, policy: dict[str, Any]) -> bool:
        if not bool(policy.get("enabled")):
            return False
        turn_offsets = policy.get("turn_offsets", []) or []
        if self.state.turn in turn_offsets:
            return True
        return self._rng.random() < float(policy.get("probability", 0.0))

    def _apply_stress_behaviors(
        self,
        *,
        text: str,
        stress_markers: list[str],
        stress_detail: dict[str, Any],
        call_taker_text: str,
    ) -> str:
        if int(self._stress_cfg.get("stress_level", 0)) <= 0:
            return text

        out = text
        non_resp = self._stress_cfg.get("non_responsive_policy", {})
        if self._policy_triggers(non_resp):
            mode = str(non_resp.get("mode", "silent")).lower()
            stress_markers.append("non_responsive")
            stress_detail["non_responsive"] = {"mode": mode}
            return "" if mode == "silent" else str(non_resp.get("non_verbal_text", "..."))

        contradiction = self._stress_cfg.get("contradiction_policy", {})
        contradiction_field = str(contradiction.get("field", "current_location"))
        contradiction_key = f"{contradiction_field}@{self.state.turn}"
        if self._policy_triggers(contradiction) and not self.state.contradiction_emitted.get(contradiction_key):
            out = f"{out} {str(contradiction.get('text', 'Wait, that may not be right.'))}".strip()
            self.state.contradiction_emitted[contradiction_key] = True
            stress_markers.append("contradiction")
            stress_detail["contradiction"] = {"field": contradiction_field}

        digression = self._stress_cfg.get("topic_digression_policy", {})
        if self._policy_triggers(digression):
            dig_text = str(digression.get("text", "Please hurry, I am panicking."))
            out = f"{dig_text} {out}".strip()
            stress_markers.append("topic_digression")
            stress_detail["topic_digression"] = {"text": dig_text}

        interruption = self._stress_cfg.get("interruption_policy", {})
        if self._policy_triggers(interruption):
            frag = str(interruption.get("fragment", "Wait, sorry, listen."))
            out = f"{out} {frag}".strip()
            stress_markers.append("interruption")
            stress_detail["interruption"] = {"fragment": frag, "call_taker_len": len(call_taker_text)}

        return out
