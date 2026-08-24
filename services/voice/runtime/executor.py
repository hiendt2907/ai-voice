"""ScriptRuntime — executes a call script step by step.

Drives the session FSM given a script body and a stream of user utterances.
Pure logic, no I/O: all side-effects (TTS, STT, Redis) are injected externally.

`process_turn` is the sync path (tests, mock replay).
`async_process_turn` is the production path with LLM NLU + 800ms fallback.
"""

from __future__ import annotations

import logging
import random
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from nlu.slot_extractor import format_hour_vn
from runtime.fsm import resolve_next_step
from runtime.intent_matcher import MatchResult, match_intent
from runtime.session import SessionState, TranscriptEntry

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
    nlu_confidence: float = 0.0
    nlu_tier: str = ""


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
            derived["time_slot"] = f"buổi {tod} lúc {format_hour_vn(hour)}"
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


# TEMPORARY placeholder for a real merchant-calendar availability lookup —
# there is no merchant API integration yet (planned separately). Picks a
# plausible clinic-hours slot so the flow doesn't stall asking the caller to
# guess a free hour themselves; replace `_mock_pick_available_slot` with an
# actual API call once that integration lands.
#
# CẢNH BÁO — KHÔNG PHẢI GIỜ LÀM VIỆC THẬT: danh sách này chỉ có khung sáng
# (8:00-10:00) và chiều (14:00-16:00), KHÔNG có khung tối, và không kiểm tra
# thứ trong tuần hay ngày lễ (kể cả Chủ nhật). Đây là dữ liệu placeholder
# thuần kỹ thuật để flow không bị đứng khi khách chưa nói giờ cụ thể — TUYỆT
# ĐỐI không coi là nguồn giờ làm việc đáng tin. Người vận hành phòng khám
# phải xác nhận giờ làm việc thật (có khám buổi tối không, Chủ nhật có mở
# cửa không, v.v.) trước khi thay đổi danh sách này; việc đó nằm ngoài phạm
# vi của đợt sửa lỗi trích xuất slot này.
_MOCK_AVAILABLE_HOURS = ["8:00", "8:30", "9:00", "9:30", "10:00", "14:00", "14:30", "15:00", "15:30", "16:00"]


def _mock_pick_available_slot() -> dict[str, str]:
    hour = random.choice(_MOCK_AVAILABLE_HOURS)
    time_of_day = "sáng" if int(hour.split(":")[0]) < 12 else "chiều"
    return {"appointment_hour": hour, "time_of_day": time_of_day}


_TIME_SLOT_KEYS = ["time_slot", "appointment_hour", "time_of_day"]


def _clear_stale_time_on_rejection(
    state: SessionState, next_step_id: str | None, intent: str | None, new_slots: dict[str, str]
) -> SessionState:
    """Caller rejected the offered time (deny/change_time) — drop the old
    time_slot/appointment_hour/time_of_day and keep only whatever the SAME
    utterance freshly gave (if anything), then recompute time_slot from
    that. Without this, giving only a new time_of_day ("buổi sáng") while
    the old appointment_hour ("9:30") survives untouched recomputes back to
    the exact same time_slot string, and the multi-slot skip bounces
    straight back to confirm_time_available re-reading the SAME rejected
    offer verbatim — a caller saying just "buổi sáng" clearly wants a new
    hour picked within that period, not to keep the old one silently."""
    if next_step_id != "collect_time" or intent not in ("deny", "change_time"):
        return state
    cleared = state.without_slots(_TIME_SLOT_KEYS)
    fresh = {k: v for k, v in new_slots.items() if k in _TIME_SLOT_KEYS}
    if not fresh:
        return cleared
    cleared = cleared.with_slots(fresh)
    derived = _recompute_derived_slots(dict(cleared.slots))
    return cleared.with_slots(derived) if derived else cleared


def _fill_time_slot_if_landing_unset(state: SessionState, next_step_id: str | None) -> SessionState:
    """Caller gave a date but never specified a time — mock-assign an
    available slot instead of making them guess an exact hour.

    The `state.slots.get("time_slot")` guard is what keeps this from ever
    clobbering a time the caller actually stated: `time_slot` is derived by
    `_recompute_derived_slots` from `time_of_day`/`appointment_hour` and
    merged into `state` BEFORE this function runs (see `_process_with_match`
    / `process_turn`), so it is already truthy the moment either of those two
    slots was extracted from the utterance — this turn's or an earlier one's.
    Verified against the real persona-97 transcript (khách nói rõ "buổi tối"
    + "7 rưỡi" hai lần): after fixing the time_of_day/"tối đa" and
    hour/"rưỡi" extraction bugs, this mock path never fires for that call —
    confirmed via tests/test_slot_recovery.py's mock-does-not-override cases."""
    if next_step_id != "confirm_time_available" or state.slots.get("time_slot"):
        return state
    state = state.with_slots(_mock_pick_available_slot())
    derived = _recompute_derived_slots(dict(state.slots))
    return state.with_slots(derived) if derived else state


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
        state = _clear_stale_time_on_rejection(state, next_step_id, intent, new_slots)
        state = _fill_time_slot_if_landing_unset(state, next_step_id)
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
        state = _clear_stale_time_on_rejection(state, next_step_id, intent, new_slots)
        state = _fill_time_slot_if_landing_unset(state, next_step_id)
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
) -> TurnResult:
    """Async version with stateful LLM NLU (primary) + vector NLU (fallback)."""
    if not utterance:
        return process_turn(state, script_body, utterance)

    # Extract current step context — used by both LLM and vector NLU
    from runtime.fsm import extract_step_intents  # noqa: PLC0415
    _steps_map = _step_index(script_body)
    _cur_step = _steps_map.get(state.current_step_id, {})
    _expected_intents = extract_step_intents(_cur_step)
    campaign_id: str | None = script_body.get("campaignId")

    # Primary: per-turn vector NLU (local embedding similarity, single-digit
    # ms). The stateful LLM resolver used to run first and unconditionally —
    # it ignored the `use_llm_nlu` setting entirely — which put a full cloud
    # LLM round-trip (~2s against xKiro) in front of *every* turn even when
    # the local matcher would have answered instantly.
    nlu_result = None
    try:
        import asyncio  # noqa: PLC0415

        from nlu.intent_resolver import resolve as nlu_resolve  # noqa: PLC0415
        from rag.embedder import embed_query  # noqa: PLC0415

        loop = asyncio.get_running_loop()
        query_emb = await loop.run_in_executor(None, embed_query, utterance)
        nlu_result = nlu_resolve(
            utterance, query_emb,
            campaign_id=campaign_id,
            expected_intents=_expected_intents or None,
        )
        logger.info(
            "Vector NLU: intent=%s confidence=%.3f tier=%s",
            nlu_result.intent, nlu_result.confidence, nlu_result.tier,
        )
    except Exception as vec_exc:
        logger.warning("Vector NLU failed: %s", vec_exc)

    # Escalate to the stateful LLM resolver only when the local matcher isn't
    # confident — it sees the whole conversation history, so it resolves
    # context-dependent turns vector NLU can't, but it is ~100x slower.
    from api.config import Settings as _Settings  # noqa: PLC0415
    if _Settings().use_llm_nlu and (nlu_result is None or nlu_result.tier != "confident"):
        try:
            from nlu.llm_resolver import resolve_with_llm  # noqa: PLC0415
            llm_result = await resolve_with_llm(utterance, state, script_body, _expected_intents)
            if llm_result is not None:
                nlu_result = llm_result
        except Exception as llm_exc:
            logger.info(
                "LLM NLU unavailable [%s] %r, keeping vector NLU result",
                type(llm_exc).__name__, llm_exc,
            )

    # Slot-recovery retry: a step whose only way forward needs a specific
    # slot (e.g. collect_date needs slot.appointment_date) can be stuck in a
    # blind reprompt loop even when the intent tier reported "confident" —
    # that tier reflects the confidence of the (possibly wrong) intent match,
    # not whether the slot the FSM actually checks got filled. Try once to
    # recover the missing slot using the full conversation as context before
    # falling through to the ordinary reprompt/handoff path.
    if _Settings().use_llm_nlu and nlu_result is not None:
        from runtime.fsm import extract_step_required_slots  # noqa: PLC0415

        _required_slots = extract_step_required_slots(_cur_step)
        _have_slots = {**state.slots, **nlu_result.slots}
        _missing_slots = [s for s in _required_slots if not _have_slots.get(s)]
        if _missing_slots:
            try:
                from nlu.llm_resolver import correct_utterance_with_context  # noqa: PLC0415
                from nlu.slot_extractor import extract_slots as _retry_extract_slots  # noqa: PLC0415

                corrected = await correct_utterance_with_context(utterance, state, _missing_slots)
                if corrected != utterance:
                    retried_slots = _retry_extract_slots(corrected)
                    recovered = {
                        k: v for k, v in retried_slots.items() if k in _missing_slots and v
                    }
                    if recovered:
                        logger.info(
                            "Slot recovery via STT context-correction: step=%s "
                            "missing=%s original=%.40r corrected=%.40r recovered=%s",
                            state.current_step_id, _missing_slots, utterance, corrected, recovered,
                        )
                        import dataclasses as _dc_slots  # noqa: PLC0415
                        nlu_result = _dc_slots.replace(
                            nlu_result, slots={**nlu_result.slots, **recovered}
                        )
            except Exception as recovery_exc:
                logger.info("Slot recovery unavailable: %s", recovery_exc)

    if nlu_result is not None:
        # Convert to MatchResult for the existing FSM engine
        override = MatchResult(
            intent=nlu_result.intent,
            slots=nlu_result.slots,
            confidence=nlu_result.confidence,
        )
        result = _process_with_match(state, script_body, utterance, override)
        import dataclasses as _dc  # noqa: PLC0415
        result = _dc.replace(result, nlu_confidence=nlu_result.confidence, nlu_tier=nlu_result.tier)

        # Phase E: advance past steps whose slots are now filled (multi-slot).
        # Must NOT gate on this turn's nlu_result.slots — _advance_past_filled_steps
        # checks cumulative state.slots, so a slot filled several turns ago (e.g.
        # caller volunteers name+phone early, then just says "đúng" later) still
        # needs this to run even though the current turn added nothing new.
        if result.next_step_id is not None:
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
        # Skip when slots were extracted: slot-fill utterances naturally have low intent confidence
        if nlu_result.tier == "handoff" and not nlu_result.slots and not result.is_completed and not result.is_handoff:
            steps_map = _step_index(script_body)
            current_step = steps_map.get(result.state.current_step_id, {})
            fallback_goto = current_step.get("fallback_goto")
            if fallback_goto:
                import dataclasses  # noqa: PLC0415
                advanced = result.state.with_step(fallback_goto)
                result = dataclasses.replace(result, state=advanced, next_step_id=fallback_goto, is_handoff=True)

        return result

    # Final fallback: sync substring matcher
    return process_turn(state, script_body, utterance)
