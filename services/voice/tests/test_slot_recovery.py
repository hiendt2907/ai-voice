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
