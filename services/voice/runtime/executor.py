"""ScriptRuntime — executes a call script step by step.

Drives the session FSM given a script body and a stream of user utterances.
Pure logic, no I/O: all side-effects (TTS, STT, Redis) are injected externally.

`process_turn` is the sync path (tests, mock replay).
`async_process_turn` is the production path with LLM NLU + 800ms fallback.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from runtime.fsm import resolve_next_step
from runtime.intent_matcher import MatchResult, match_intent
from runtime.session import SessionState, TranscriptEntry
from nlu.slot_extractor import extract_slots as nlu_extract_slots

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnResult:
    agent_text: str
    intent: str | None
    slots: dict[str, str]
    next_step_id: str | None
    is_handoff: bool
    is_completed: bool
    state: SessionState
    suggested_filler: str = "thinking"
    filler_slot_value: str = ""


_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")


def _render_beats(beats: list[dict[str, Any]], slots: dict[str, str]) -> str:
    """Concatenate beat texts, replacing {{var}} with slot values."""
    parts = []
    for beat in beats:
        text: str = beat.get("text", "")
        text = _TEMPLATE_VAR.sub(lambda m: slots.get(m.group(1), m.group(0)), text)
        parts.append(text)
    return " ".join(parts)


def _recompute_derived_slots(slots: dict[str, str]) -> dict[str, str]:
    """Recompute derived slots that depend on other slots.

    Called after every slot update so template vars like {{time_slot}} are
    always consistent with the latest time_of_day + appointment_hour values.
    """
    derived: dict[str, str] = {}
    tod = slots.get("time_of_day")
    hour = slots.get("appointment_hour")
    if tod:
        if hour:
            derived["time_slot"] = f"buổi {tod} lúc {hour} giờ"
        else:
            derived["time_slot"] = f"buổi {tod}"
    noisoi_type = slots.get("noisoi_type")
    if noisoi_type:
        _labels = {"da_day": "dạ dày", "dai_trang": "đại tràng", "combo": "dạ dày và đại tràng"}
        derived["noisoi_type_label"] = _labels.get(noisoi_type, "nội soi")
    return derived


def _pick_variant(variants: list[dict], no_match_count: int) -> dict:
    """Pick a variant. For reprompts, cycle through variants."""
    if not variants:
        return {}
    idx = no_match_count % len(variants)
    return variants[idx]


def _advance_past_filled_steps(
    state: SessionState,
    steps: dict[str, dict],
    max_hops: int = 10,
) -> SessionState:
    """Advance the FSM past steps whose required slots are already filled.

    When a user provides multiple slots in a single utterance (e.g. name +
    specialty + date), subsequent collection steps become redundant. This
    function walks forward through unconditional transitions whose conditions
    are satisfied by the current slot state — stopping when it reaches a step
    that still has an unfilled slot requirement or a terminal step.

    max_hops guards against infinite loops in malformed scripts.
    """
    for _ in range(max_hops):
        step = steps.get(state.current_step_id)
        if step is None or step.get("type", "speak") in ("speak", "handoff", "hangup"):
            break
        # Check if all transitions would fire immediately (slots already filled)
        transitions: list[dict] = step.get("transitions", [])
        fired_goto: str | None = None
        for t in transitions:
            from runtime.fsm import evaluate_condition  # noqa: PLC0415
            if evaluate_condition(t["when"], None, dict(state.slots)):
                fired_goto = t["goto"]
                break
        if fired_goto is None:
            break
        state = state.with_step(fired_goto)
    return state


def _step_index(script_body: dict) -> dict[str, dict]:
    return {s["id"]: s for s in script_body.get("steps", [])}


def _suggest_filler(intent: str | None, new_slots: dict[str, str]) -> tuple[str, str]:
    """Suggest the best filler context based on turn outcome.

    Returns (filler_context, slot_value_to_echo).
    """
    if intent is None:
        return "thinking", ""
    if new_slots:
        first_key = next(iter(new_slots))
        return "ack_slot", new_slots[first_key]
    return "ack", ""


_WEEKDAYS_VN = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ Nhật"]


def _weekday_vn(weekday: int) -> str:
    return _WEEKDAYS_VN[weekday]


def create_session(script_body: dict) -> SessionState:
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    steps = script_body.get("steps", [])
    first_step_id = steps[0]["id"] if steps else ""
    date_slots = {
        "today_date": f"{now.day:02d}/{now.month:02d}/{now.year}",
        "today_weekday": _weekday_vn(now.weekday()),
        "today_full": f"{_weekday_vn(now.weekday())}, ngày {now.day:02d} tháng {now.month:02d}",
        "tomorrow_date": f"{tomorrow.day:02d}/{tomorrow.month:02d}/{tomorrow.year}",
        "tomorrow_full": f"{_weekday_vn(tomorrow.weekday())}, ngày {tomorrow.day:02d} tháng {tomorrow.month:02d}",
    }
    return SessionState(
        session_id=str(uuid.uuid4()),
        script_id=str(script_body.get("id", "")),
        current_step_id=str(script_body.get("entry_step", first_step_id)),
        slots=date_slots,
    )


def _process_with_match(
    state: SessionState,
    script_body: dict,
    utterance: str | None,
    match: MatchResult,
) -> TurnResult:
    """Process a turn using a pre-computed MatchResult (used by async path)."""
    steps = _step_index(script_body)
    step = steps.get(state.current_step_id)

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

    no_match_count = state.get_no_match_count(state.current_step_id)

    if no_match_count > 0 and step.get("reprompt_variants"):
        reprompts: list[dict] = step["reprompt_variants"]
        variant = _pick_variant(reprompts, no_match_count - 1)
    else:
        variant = _pick_variant(step.get("variants", []), 0)

    beats: list[dict] = variant.get("beats", [])
    agent_text = _render_beats(beats, state.slots)

    state = state.with_transcript_entry(
        TranscriptEntry(step_id=state.current_step_id, role="agent", text=agent_text)
    )

    step_type: str = step.get("type", "speak")
    if step_type in ("speak", "handoff", "hangup"):
        is_handoff = step_type == "handoff"
        is_completed = step_type in ("speak", "hangup")
        new_status = "handoff" if is_handoff else "completed"
        state = state.with_status(new_status)  # type: ignore[arg-type]
        return TurnResult(
            agent_text=agent_text, intent=None, slots={}, next_step_id=None,
            is_handoff=is_handoff, is_completed=is_completed, state=state,
        )

    intent = match.intent
    new_slots = match.slots
    if utterance:
        state = state.with_slots(new_slots)
        derived = _recompute_derived_slots(dict(state.slots))
        if derived:
            state = state.with_slots(derived)
        state = state.with_transcript_entry(
            TranscriptEntry(step_id=state.current_step_id, role="user", text=utterance, intent=intent)
        )

    next_step_id, _ = resolve_next_step(step, intent, state.slots, no_match_count)
    if next_step_id is not None:
        state = state.with_step(next_step_id)
    else:
        state = state.increment_no_match(state.current_step_id)

    suggested_filler, filler_slot_value = _suggest_filler(intent, new_slots)
    return TurnResult(
        agent_text=agent_text, intent=intent, slots=new_slots,
        next_step_id=next_step_id, is_handoff=False, is_completed=False, state=state,
        suggested_filler=suggested_filler, filler_slot_value=filler_slot_value,
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
        derived = _recompute_derived_slots(dict(state.slots))
        if derived:
            state = state.with_slots(derived)
        state = state.with_transcript_entry(
            TranscriptEntry(step_id=state.current_step_id, role="user", text=utterance, intent=intent)
        )

    next_step_id, is_fallback = resolve_next_step(step, intent, state.slots, no_match_count)

    if next_step_id is not None:
        state = state.with_step(next_step_id)
    else:
        # Still within reprompt budget
        state = state.increment_no_match(state.current_step_id)

    suggested_filler, filler_slot_value = _suggest_filler(intent, new_slots)
    return TurnResult(
        agent_text=agent_text,
        intent=intent,
        slots=new_slots,
        next_step_id=next_step_id,
        is_handoff=False,
        is_completed=False,
        state=state,
        suggested_filler=suggested_filler,
        filler_slot_value=filler_slot_value,
    )


async def async_process_turn(
    state: SessionState,
    script_body: dict,
    utterance: str | None,
    nlu: "Any | None" = None,
) -> TurnResult:
    """Async version with vector NLU + multi-slot extraction + confidence gradient."""
    if not utterance:
        return process_turn(state, script_body, utterance)

    # Vector NLU path
    try:
        import asyncio  # noqa: PLC0415
        from rag.embedder import embed_query  # noqa: PLC0415
        from nlu.intent_resolver import resolve as nlu_resolve, CONFIDENT_THRESHOLD, CLARIFY_THRESHOLD  # noqa: PLC0415

        loop = asyncio.get_running_loop()
        query_emb = await loop.run_in_executor(None, embed_query, utterance)
        campaign_id: str | None = script_body.get("campaignId")
        nlu_result = nlu_resolve(utterance, query_emb, campaign_id=campaign_id)

        logger.debug(
            "NLU: intent=%s confidence=%.3f tier=%s",
            nlu_result.intent, nlu_result.confidence, nlu_result.tier,
        )

        # Convert to MatchResult for the existing FSM engine
        override = MatchResult(
            intent=nlu_result.intent,
            slots=nlu_result.slots,
            confidence=nlu_result.confidence,
        )
        result = _process_with_match(state, script_body, utterance, override)

        # Phase E: advance past steps whose slots are now filled (multi-slot)
        if nlu_result.slots and result.next_step_id is not None:
            steps = _step_index(script_body)
            advanced_state = _advance_past_filled_steps(result.state, steps)
            if advanced_state.current_step_id != result.state.current_step_id:
                logger.debug(
                    "Multi-slot skip: %s → %s",
                    result.state.current_step_id,
                    advanced_state.current_step_id,
                )
                import dataclasses  # noqa: PLC0415
                result = dataclasses.replace(
                    result,
                    state=advanced_state,
                    next_step_id=advanced_state.current_step_id,
                )

        # Phase D: confidence gradient — low confidence → trigger expert handoff
        if nlu_result.tier == "handoff" and not result.is_completed and not result.is_handoff:
            steps_map = _step_index(script_body)
            current_step = steps_map.get(result.state.current_step_id, {})
            fallback_goto = current_step.get("fallback_goto")
            if fallback_goto:
                import dataclasses  # noqa: PLC0415
                advanced = result.state.with_step(fallback_goto)
                result = dataclasses.replace(result, state=advanced, next_step_id=fallback_goto, is_handoff=True)

        return result

    except Exception as exc:
        logger.warning("Vector NLU failed, using fallback matcher: %s", exc)

    # Fallback: LLM NLU (if configured)
    if nlu is not None:
        intents: list[dict] = script_body.get("intents", [])
        try:
            from llm.nlu import LLMNLUClassifier  # noqa: PLC0415
            if isinstance(nlu, LLMNLUClassifier):
                llm_result = await nlu.classify_intent(utterance, intents, dict(state.slots))
                override = MatchResult(intent=llm_result.intent, slots=llm_result.slots, confidence=llm_result.confidence)
                return _process_with_match(state, script_body, utterance, override)
        except Exception as exc2:
            logger.warning("LLM NLU also failed: %s", exc2)

    # Final fallback: sync substring matcher
    return process_turn(state, script_body, utterance)
