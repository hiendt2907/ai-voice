"""ScriptRuntime — executes a call script step by step.

Drives the session FSM given a script body and a stream of user utterances.
Pure logic, no I/O: all side-effects (TTS, STT, Redis) are injected externally.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from runtime.fsm import resolve_next_step
from runtime.intent_matcher import match_intent
from runtime.session import SessionState, TranscriptEntry


@dataclass(frozen=True)
class TurnResult:
    agent_text: str
    intent: str | None
    slots: dict[str, str]
    next_step_id: str | None
    is_handoff: bool
    is_completed: bool
    state: SessionState


_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")


def _render_beats(beats: list[dict[str, Any]], slots: dict[str, str]) -> str:
    """Concatenate beat texts, replacing {{var}} with slot values."""
    parts = []
    for beat in beats:
        text: str = beat.get("text", "")
        text = _TEMPLATE_VAR.sub(lambda m: slots.get(m.group(1), m.group(0)), text)
        parts.append(text)
    return " ".join(parts)


def _pick_variant(variants: list[dict], no_match_count: int) -> dict:
    """Pick a variant. For reprompts, cycle through variants."""
    if not variants:
        return {}
    idx = no_match_count % len(variants)
    return variants[idx]


def _step_index(script_body: dict) -> dict[str, dict]:
    return {s["id"]: s for s in script_body.get("steps", [])}


def create_session(script_body: dict) -> SessionState:
    return SessionState(
        session_id=str(uuid.uuid4()),
        script_id=str(script_body.get("id", "")),
        current_step_id=str(script_body.get("entry_step", "")),
    )


def process_turn(
    state: SessionState,
    script_body: dict,
    utterance: str | None,
) -> TurnResult:
    """Process one turn: speak agent text, process utterance, compute next step."""
    steps = _step_index(script_body)
    step = steps.get(state.current_step_id)
    intents: list[dict] = script_body.get("intents", [])

    if step is None:
        return TurnResult(
            agent_text="",
            intent=None,
            slots={},
            next_step_id=None,
            is_handoff=False,
            is_completed=True,
            state=state.with_status("completed"),
        )

    step_type: str = step.get("type", "speak")
    no_match_count = state.get_no_match_count(state.current_step_id)

    # Pick which variant to speak
    if no_match_count > 0 and step.get("reprompt_variants"):
        reprompts: list[dict] = step["reprompt_variants"]
        variant = _pick_variant(reprompts, no_match_count - 1)
    else:
        variant = _pick_variant(step.get("variants", []), 0)

    beats: list[dict] = variant.get("beats", [])
    agent_text = _render_beats(beats, state.slots)

    # Record agent turn in transcript
    state = state.with_transcript_entry(
        TranscriptEntry(step_id=state.current_step_id, role="agent", text=agent_text)
    )

    # Terminal steps — no listening needed
    if step_type in ("speak", "handoff", "hangup"):
        is_handoff = step_type == "handoff"
        is_completed = step_type in ("speak", "hangup")
        new_status = "handoff" if is_handoff else "completed"
        state = state.with_status(new_status)  # type: ignore[arg-type]
        return TurnResult(
            agent_text=agent_text,
            intent=None,
            slots={},
            next_step_id=None,
            is_handoff=is_handoff,
            is_completed=is_completed,
            state=state,
        )

    # speak_listen: process utterance
    intent: str | None = None
    new_slots: dict[str, str] = {}

    if utterance:
        match = match_intent(utterance, intents)
        intent = match.intent
        new_slots = match.slots
        state = state.with_slots(new_slots)
        state = state.with_transcript_entry(
            TranscriptEntry(step_id=state.current_step_id, role="user", text=utterance, intent=intent)
        )

    next_step_id, is_fallback = resolve_next_step(step, intent, state.slots, no_match_count)

    if next_step_id is not None:
        state = state.with_step(next_step_id)
    else:
        # Still within reprompt budget
        state = state.increment_no_match(state.current_step_id)

    return TurnResult(
        agent_text=agent_text,
        intent=intent,
        slots=new_slots,
        next_step_id=next_step_id,
        is_handoff=False,
        is_completed=False,
        state=state,
    )
