"""Tests for ScriptRuntime — session, FSM, intent matcher, executor."""

import pytest
from runtime.session import SessionState, TranscriptEntry
from runtime.fsm import evaluate_condition, resolve_next_step
from runtime.intent_matcher import match_intent
from runtime.executor import create_session, process_turn

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_SCRIPT = {
    "id": "00000000-0000-0000-0000-000000000001",
    "version": "1.0.0",
    "campaign_id": "00000000-0000-0000-0000-000000000010",
    "direction": "inbound",
    "voice_profile": "linh_clone_v1",
    "entry_step": "greeting",
    "steps": [
        {
            "id": "greeting",
            "type": "speak_listen",
            "variants": [
                {"id": "v1", "beats": [{"text": "Xin chào, tôi có thể hỗ trợ gì?", "pause_after": "turn"}]}
            ],
            "reprompt_variants": [
                {"id": "r1", "beats": [{"text": "Bạn cần hỗ trợ gì không?", "pause_after": "turn"}]},
                {"id": "r2", "beats": [{"text": "Tôi vẫn đang nghe.", "pause_after": "turn"}]},
                {"id": "r3", "beats": [{"text": "Tôi chuyển bạn sang nhân viên.", "pause_after": "turn"}]},
            ],
            "transitions": [
                {"when": "intent == 'book_appointment'", "goto": "farewell"},
            ],
            "fallback_goto": "farewell",
            "max_no_match": 3,
        },
        {
            "id": "farewell",
            "type": "speak",
            "variants": [
                {"id": "v1", "beats": [{"text": "Cảm ơn bạn. Chúc sức khỏe.", "pause_after": "long"}]}
            ],
        },
    ],
    "intents": [
        {
            "intent": "book_appointment",
            "examples": [
                {"text": "tôi muốn đặt lịch"},
                {"text": "đặt hẹn khám"},
                {"text": "cho tôi đặt lịch"},
            ],
        },
    ],
}

SLOT_SCRIPT = {
    **MINIMAL_SCRIPT,
    "steps": [
        {
            "id": "greeting",
            "type": "speak_listen",
            "variants": [{"id": "v1", "beats": [{"text": "Hỏi gì?", "pause_after": "turn"}]}],
            "reprompt_variants": [
                {"id": "r1", "beats": [{"text": "R1", "pause_after": "turn"}]},
                {"id": "r2", "beats": [{"text": "R2", "pause_after": "turn"}]},
                {"id": "r3", "beats": [{"text": "R3", "pause_after": "turn"}]},
            ],
            "transitions": [{"when": "slot.date != null", "goto": "confirm"}],
            "fallback_goto": "confirm",
            "max_no_match": 3,
        },
        {
            "id": "confirm",
            "type": "speak",
            "variants": [
                {"id": "v1", "beats": [{"text": "Lịch vào {{date}}.", "pause_after": "medium"}]}
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# SessionState tests
# ---------------------------------------------------------------------------


def test_session_state_immutability():
    s1 = SessionState(session_id="abc", script_id="s1", current_step_id="greeting")
    s2 = s1.with_step("farewell")
    assert s1.current_step_id == "greeting"
    assert s2.current_step_id == "farewell"


def test_session_state_slots_merge():
    s = SessionState(session_id="abc", script_id="s1", current_step_id="greeting")
    s1 = s.with_slots({"date": "ngày 15"})
    s2 = s1.with_slots({"time_of_day": "sáng"})
    assert s2.slots == {"date": "ngày 15", "time_of_day": "sáng"}
    assert s1.slots == {"date": "ngày 15"}  # original unchanged


def test_session_increment_no_match():
    s = SessionState(session_id="abc", script_id="s1", current_step_id="greeting")
    s1 = s.increment_no_match("greeting")
    s2 = s1.increment_no_match("greeting")
    assert s2.get_no_match_count("greeting") == 2
    assert s.get_no_match_count("greeting") == 0


def test_session_transcript_append():
    s = SessionState(session_id="abc", script_id="s1", current_step_id="greeting")
    entry = TranscriptEntry(step_id="greeting", role="agent", text="Xin chào")
    s2 = s.with_transcript_entry(entry)
    assert len(s2.transcript) == 1
    assert len(s.transcript) == 0  # original unchanged


# ---------------------------------------------------------------------------
# FSM tests
# ---------------------------------------------------------------------------


def test_evaluate_intent_eq_match():
    assert evaluate_condition("intent == 'book_appointment'", "book_appointment", {}) is True


def test_evaluate_intent_eq_no_match():
    assert evaluate_condition("intent == 'book_appointment'", "cancel", {}) is False


def test_evaluate_intent_eq_none():
    assert evaluate_condition("intent == 'book_appointment'", None, {}) is False


def test_evaluate_slot_not_null_present():
    assert evaluate_condition("slot.date != null", None, {"date": "ngày 15"}) is True


def test_evaluate_slot_not_null_absent():
    assert evaluate_condition("slot.date != null", None, {}) is False


def test_evaluate_slot_is_null():
    assert evaluate_condition("slot.date == null", None, {}) is True
    assert evaluate_condition("slot.date == null", None, {"date": "x"}) is False


def test_evaluate_unknown_condition():
    assert evaluate_condition("some_unknown_condition", "intent", {}) is False


def test_resolve_next_step_transition_fires():
    step = {
        "transitions": [{"when": "intent == 'book_appointment'", "goto": "collect_date"}],
        "fallback_goto": "handoff",
        "max_no_match": 3,
    }
    next_id, is_fallback = resolve_next_step(step, "book_appointment", {}, 0)
    assert next_id == "collect_date"
    assert is_fallback is False


def test_resolve_next_step_no_match_reprompt():
    step = {
        "transitions": [{"when": "intent == 'book_appointment'", "goto": "collect_date"}],
        "fallback_goto": "handoff",
        "max_no_match": 3,
    }
    # First no-match — still within budget
    next_id, is_fallback = resolve_next_step(step, None, {}, 0)
    assert next_id is None
    assert is_fallback is False


def test_resolve_next_step_fallback_on_exhaustion():
    step = {
        "transitions": [{"when": "intent == 'book_appointment'", "goto": "collect_date"}],
        "fallback_goto": "handoff",
        "max_no_match": 3,
    }
    # Third no-match — fallback
    next_id, is_fallback = resolve_next_step(step, None, {}, 2)
    assert next_id == "handoff"
    assert is_fallback is True


# ---------------------------------------------------------------------------
# Intent matcher tests
# ---------------------------------------------------------------------------


def test_match_book_appointment():
    intents = MINIMAL_SCRIPT["intents"]
    result = match_intent("tôi muốn đặt lịch khám bác sĩ", intents)
    assert result.intent == "book_appointment"


def test_match_no_match():
    intents = MINIMAL_SCRIPT["intents"]
    result = match_intent("blah blah blah", intents)
    assert result.intent is None


def test_leading_confirm_outranks_embedded_intent_keyword():
    """Caught by a dynamic LLM-caller test: caller confirms the offered
    slot ("Ừ thì đặt đi") then adds an unrelated hedge/aside later in the
    same utterance that happens to contain "đổi giờ" — the leading direct
    reply must win, not the longer embedded substring, or the just-confirmed
    appointment gets silently wiped."""
    intents = [
        {"intent": "confirm", "examples": [{"text": "ừ"}, {"text": "đúng rồi"}, {"text": "ok"}]},
        {"intent": "change_time", "examples": [{"text": "đổi giờ"}, {"text": "giờ khác"}]},
    ]
    result = match_intent(
        "Ừ thì đặt đi, nhưng nhớ báo trước là tôi hay đổi giờ lắm, "
        "nếu bác sĩ nào không linh hoạt thì bảo em chuyển ngay cho người khác nhé. Cảm ơn.",
        intents,
    )
    assert result.intent == "confirm"


def test_embedded_intent_keyword_still_matches_without_leading_confirm():
    intents = [
        {"intent": "confirm", "examples": [{"text": "ừ"}, {"text": "đúng rồi"}, {"text": "ok"}]},
        {"intent": "change_time", "examples": [{"text": "đổi giờ"}, {"text": "giờ khác"}]},
    ]
    result = match_intent("đổi giờ được không", intents)
    assert result.intent == "change_time"


def test_extract_date_slot():
    result = match_intent("ngày 15 tháng 6", [])
    assert result.slots.get("appointment_date") is not None
    assert "15" in result.slots["appointment_date"]


def test_extract_time_of_day_morning():
    result = match_intent("tôi muốn khám buổi sáng", [])
    assert result.slots.get("time_of_day") == "sáng"


def test_extract_time_of_day_afternoon():
    result = match_intent("buổi chiều được không", [])
    assert result.slots.get("time_of_day") == "chiều"


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------


def test_create_session_entry_step():
    state = create_session(MINIMAL_SCRIPT)
    assert state.current_step_id == "greeting"
    assert state.status == "active"
    assert len(state.transcript) == 0


def test_process_turn_speak_listen_match():
    state = create_session(MINIMAL_SCRIPT)
    result = process_turn(state, MINIMAL_SCRIPT, "tôi muốn đặt lịch")
    assert "Xin chào" in result.agent_text
    assert result.intent == "book_appointment"
    assert result.next_step_id == "farewell"
    assert result.is_completed is False
    assert result.is_handoff is False


def test_process_turn_speak_terminates():
    state = create_session(MINIMAL_SCRIPT).with_step("farewell")
    result = process_turn(state, MINIMAL_SCRIPT, None)
    assert "Cảm ơn" in result.agent_text
    assert result.is_completed is True
    assert result.next_step_id is None


def test_process_turn_reprompt_on_no_match():
    state = create_session(MINIMAL_SCRIPT)
    result = process_turn(state, MINIMAL_SCRIPT, "tôi không hiểu")
    assert result.next_step_id is None
    assert result.state.get_no_match_count("greeting") == 1


def test_process_turn_slot_template_rendering():
    state = create_session(SLOT_SCRIPT).with_slots({"date": "ngày 15 tháng 6"}).with_step("confirm")
    result = process_turn(state, SLOT_SCRIPT, None)
    assert "ngày 15 tháng 6" in result.agent_text


def test_session_is_immutable_across_turns():
    state1 = create_session(MINIMAL_SCRIPT)
    result = process_turn(state1, MINIMAL_SCRIPT, "tôi muốn đặt lịch")
    assert state1.current_step_id == "greeting"  # unchanged
    assert result.state.current_step_id == "farewell"
