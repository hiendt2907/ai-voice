"""Tests for LLM-assisted slot recovery when the regex extractor comes up
empty on a step whose only way forward requires a specific slot.

Covers the bug found via real-call testing: STT mis-hears "Hôm nay buổi
sáng" as "Hãy nay buổi sáng", the date regex can't match the corrupted
text, and the step (collect_date) — which transitions on
`slot.appointment_date != null`, not on intent — was stuck reprompting
forever even though vector NLU reported a confident (wrong) intent match.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

import nlu.store as nlu_store_module
from nlu.intent_resolver import NluResult
from nlu.llm_resolver import correct_utterance_with_context
from runtime.executor import async_process_turn, create_session
from runtime.fsm import extract_step_required_slots
from runtime.session import SessionState, TranscriptEntry


@pytest.fixture(autouse=True)
def isolate_nlu_store():
    saved = list(nlu_store_module._store)
    nlu_store_module._store.clear()
    yield
    nlu_store_module._store.clear()
    nlu_store_module._store.extend(saved)


DATE_SCRIPT = {
    "id": "test-script",
    "entry_step": "collect_date",
    "steps": [
        {
            "id": "collect_date",
            "type": "speak_listen",
            "variants": [{"id": "v1", "beats": [{"text": "Ngày nào ạ?", "pause_after": "turn"}]}],
            "reprompt_variants": [{"id": "r1", "beats": [{"text": "R1", "pause_after": "turn"}]}],
            "transitions": [{"when": "slot.appointment_date != null", "goto": "collect_time"}],
            "fallback_goto": "handoff_to_staff",
            "max_no_match": 3,
        },
        {
            "id": "collect_time",
            "type": "speak",
            "variants": [{"id": "v1", "beats": [{"text": "OK.", "pause_after": "long"}]}],
        },
        {
            "id": "handoff_to_staff",
            "type": "handoff",
            "variants": [{"id": "v1", "beats": [{"text": "Chuyển nhân viên.", "pause_after": "long"}]}],
        },
    ],
    "intents": [{"intent": "check_availability", "examples": [{"text": "còn lịch không"}]}],
}


# ── runtime.fsm.extract_step_required_slots ─────────────────────────────────


class TestExtractStepRequiredSlots:
    def test_single_slot_condition(self):
        step = {"transitions": [{"when": "slot.appointment_date != null", "goto": "x"}]}
        assert extract_step_required_slots(step) == ["appointment_date"]

    def test_compound_condition(self):
        step = {
            "transitions": [
                {"when": "slot.appointment_date != null && slot.time_slot != null", "goto": "x"}
            ]
        }
        assert extract_step_required_slots(step) == ["appointment_date", "time_slot"]

    def test_no_slot_condition(self):
        step = {"transitions": [{"when": "intent == 'confirm'", "goto": "x"}]}
        assert extract_step_required_slots(step) == []

    def test_no_transitions(self):
        assert extract_step_required_slots({}) == []


# ── nlu.llm_resolver.correct_utterance_with_context ─────────────────────────


class TestCorrectUtteranceWithContext:
    async def test_returns_corrected_text_on_success(self):
        state = SessionState(
            session_id="s1", script_id="test-script", current_step_id="collect_date",
            transcript=(
                TranscriptEntry(step_id="collect_date", role="agent", text="Ngày nào ạ?"),
            ),
        )
        with patch(
            "nlu.llm_resolver._chat_json",
            new=AsyncMock(return_value=json.dumps({"corrected_text": "Hôm nay buổi sáng."})),
        ):
            result = await correct_utterance_with_context("Hãy nay buổi sáng.", state)
        assert result == "Hôm nay buổi sáng."

    async def test_falls_back_to_original_on_llm_error(self):
        state = SessionState(session_id="s1", script_id="test-script", current_step_id="collect_date")
        with patch(
            "nlu.llm_resolver._chat_json",
            new=AsyncMock(side_effect=TimeoutError()),
        ):
            result = await correct_utterance_with_context("Hãy nay buổi sáng.", state)
        assert result == "Hãy nay buổi sáng."

    async def test_falls_back_to_original_on_non_json(self):
        state = SessionState(session_id="s1", script_id="test-script", current_step_id="collect_date")
        with patch(
            "nlu.llm_resolver._chat_json",
            new=AsyncMock(return_value="not json"),
        ):
            result = await correct_utterance_with_context("Hãy nay buổi sáng.", state)
        assert result == "Hãy nay buổi sáng."

    async def test_missing_slots_named_in_system_prompt(self):
        """The prompt must target the slot that's actually missing, not a
        generic 'fix mishearing' instruction — otherwise the LLM has no way
        to distinguish an STT error from valid phrasing regex just doesn't
        cover."""
        state = SessionState(session_id="s1", script_id="test-script", current_step_id="collect_date")
        chat_mock = AsyncMock(return_value=json.dumps({"corrected_text": "Hai hôm nữa."}))
        with patch("nlu.llm_resolver._chat_json", new=chat_mock):
            await correct_utterance_with_context(
                "Hai bữa nữa.", state, missing_slots=["appointment_date"]
            )
        sent_messages = chat_mock.call_args.args[0]
        system_text = sent_messages[0]["content"]
        assert "ngày muốn khám" in system_text


# ── runtime.executor.async_process_turn — integration ───────────────────────


class TestSlotRecoveryIntegration:
    async def test_recovers_missing_slot_via_context_correction(self):
        state = create_session(DATE_SCRIPT)

        confident_but_no_slot = NluResult(
            intent="check_availability", slots={}, confidence=0.83, tier="confident",
        )

        with (
            patch("nlu.intent_resolver.resolve", return_value=confident_but_no_slot),
            patch("rag.embedder.embed_query", return_value=[0.0]),
            patch(
                "nlu.llm_resolver.correct_utterance_with_context",
                new=AsyncMock(return_value="Hôm nay buổi sáng."),
            ),
            patch("api.config.Settings") as mock_settings,
        ):
            mock_settings.return_value.use_llm_nlu = True
            result = await async_process_turn(state, DATE_SCRIPT, "Hãy nay buổi sáng.")

        assert result.next_step_id == "collect_time"
        assert "appointment_date" in result.state.slots

    async def test_no_recovery_attempt_when_slot_already_present(self):
        """Vector NLU already filled the slot — correction must not be called."""
        state = create_session(DATE_SCRIPT)
        confident_with_slot = NluResult(
            intent="check_availability", slots={"appointment_date": "21/08/2026"},
            confidence=0.83, tier="confident",
        )
        correction_mock = AsyncMock(return_value="should not be called")

        with (
            patch("nlu.intent_resolver.resolve", return_value=confident_with_slot),
            patch("rag.embedder.embed_query", return_value=[0.0]),
            patch("nlu.llm_resolver.correct_utterance_with_context", new=correction_mock),
            patch("api.config.Settings") as mock_settings,
        ):
            mock_settings.return_value.use_llm_nlu = True
            await async_process_turn(state, DATE_SCRIPT, "hôm nay")

        correction_mock.assert_not_called()

    async def test_no_recovery_attempt_when_flag_disabled(self):
        state = create_session(DATE_SCRIPT)
        confident_but_no_slot = NluResult(
            intent="check_availability", slots={}, confidence=0.83, tier="confident",
        )
        correction_mock = AsyncMock(return_value="Hôm nay buổi sáng.")

        with (
            patch("nlu.intent_resolver.resolve", return_value=confident_but_no_slot),
            patch("rag.embedder.embed_query", return_value=[0.0]),
            patch("nlu.llm_resolver.correct_utterance_with_context", new=correction_mock),
            patch("api.config.Settings") as mock_settings,
        ):
            mock_settings.return_value.use_llm_nlu = False
            result = await async_process_turn(state, DATE_SCRIPT, "Hãy nay buổi sáng.")

        correction_mock.assert_not_called()
        assert result.next_step_id is None  # still stuck reprompting

    async def test_recovery_failure_falls_through_to_reprompt(self):
        """Correction runs but yields nothing usable — no crash, normal reprompt path."""
        state = create_session(DATE_SCRIPT)
        confident_but_no_slot = NluResult(
            intent="check_availability", slots={}, confidence=0.83, tier="confident",
        )

        with (
            patch("nlu.intent_resolver.resolve", return_value=confident_but_no_slot),
            patch("rag.embedder.embed_query", return_value=[0.0]),
            patch(
                "nlu.llm_resolver.correct_utterance_with_context",
                new=AsyncMock(return_value="Hãy nay buổi sáng."),  # unchanged — no correction found
            ),
            patch("api.config.Settings") as mock_settings,
        ):
            mock_settings.return_value.use_llm_nlu = True
            result = await async_process_turn(state, DATE_SCRIPT, "Hãy nay buổi sáng.")

        assert result.next_step_id is None
        assert "appointment_date" not in result.state.slots


# ── Multi-slot skip must not depend on the CURRENT turn adding new slots ────
#
# Bug found via real-call testing: caller volunteers name+phone while
# answering an unrelated confirm question ("Tôi tên A, sđt ..." in reply to
# "đặt luôn nhé?"). Those slots land in state.slots but the FSM stays on the
# confirm step (intent didn't resolve confirm/deny). Two turns later the
# caller says "Dạ đúng." — intent=confirm fires, step advances to
# collect_contact — but that turn's own nlu_result.slots is empty, so the
# multi-slot-skip that should carry the FSM straight past collect_contact
# (since patient_name/phone are already filled) must not be gated on this
# turn's slots, only on the cumulative state.

CONTACT_SCRIPT = {
    "id": "contact-script",
    "entry_step": "confirm_booking",
    "steps": [
        {
            "id": "confirm_booking",
            "type": "speak_listen",
            "variants": [{"id": "v1", "beats": [{"text": "Đặt luôn nhé?", "pause_after": "turn"}]}],
            "reprompt_variants": [{"id": "r1", "beats": [{"text": "R1", "pause_after": "turn"}]}],
            "transitions": [{"when": "intent == 'confirm'", "goto": "collect_contact"}],
            "fallback_goto": "handoff_to_staff",
            "max_no_match": 3,
        },
        {
            "id": "collect_contact",
            "type": "speak_listen",
            "variants": [{"id": "v1", "beats": [{"text": "Cho xin tên và SĐT ạ.", "pause_after": "turn"}]}],
            "reprompt_variants": [{"id": "r1", "beats": [{"text": "R1", "pause_after": "turn"}]}],
            "transitions": [
                {"when": "slot.patient_name != null && slot.patient_phone != null", "goto": "done"},
            ],
            "fallback_goto": "handoff_to_staff",
            "max_no_match": 3,
        },
        {
            "id": "done",
            "type": "speak",
            "variants": [{"id": "v1", "beats": [{"text": "Xong.", "pause_after": "long"}]}],
        },
        {
            "id": "handoff_to_staff",
            "type": "handoff",
            "variants": [{"id": "v1", "beats": [{"text": "Chuyển nhân viên.", "pause_after": "long"}]}],
        },
    ],
    "intents": [
        {"intent": "confirm", "examples": [{"text": "đúng rồi"}]},
        {"intent": "deny", "examples": [{"text": "không phải"}]},
    ],
}


class TestMultiSlotSkipNotGatedOnCurrentTurnSlots:
    async def test_skips_collect_contact_when_slots_were_filled_two_turns_earlier(self):
        state = create_session(CONTACT_SCRIPT)

        # Turn A: caller volunteers name+phone while answering the confirm
        # question — intent doesn't resolve (off-topic reply), but the regex
        # extractor (called unconditionally inside resolve()) still picks up
        # the slots.
        early_slots = NluResult(
            intent=None,
            slots={"patient_name": "Nguyễn Văn A", "patient_phone": "0901234567"},
            confidence=0.3,
            tier="clarify",
        )
        with (
            patch("nlu.intent_resolver.resolve", return_value=early_slots),
            patch("rag.embedder.embed_query", return_value=[0.0]),
            patch("api.config.Settings") as mock_settings,
        ):
            mock_settings.return_value.use_llm_nlu = False
            early_result = await async_process_turn(
                state, CONTACT_SCRIPT, "Tôi tên Nguyễn Văn A, số điện thoại 0901234567."
            )
        state = early_result.state
        assert state.current_step_id == "confirm_booking"  # still stuck — intent didn't resolve
        assert state.slots.get("patient_name") == "Nguyễn Văn A"
        assert state.slots.get("patient_phone") == "0901234567"

        # Turn B: caller just confirms — this turn's own nlu_result.slots is
        # empty, but state.slots (cumulative) already satisfies collect_contact.
        confirm_only = NluResult(intent="confirm", slots={}, confidence=0.99, tier="confident")
        with (
            patch("nlu.intent_resolver.resolve", return_value=confirm_only),
            patch("rag.embedder.embed_query", return_value=[0.0]),
            patch("api.config.Settings") as mock_settings,
        ):
            mock_settings.return_value.use_llm_nlu = False
            result = await async_process_turn(state, CONTACT_SCRIPT, "Dạ đúng.")

        assert result.state.current_step_id == "done", (
            "multi-slot skip must fire off cumulative state.slots, not this turn's "
            "empty nlu_result.slots — otherwise the caller gets asked to repeat "
            "info they already gave"
        )
