"""Tests for the unified NLU stack: slot_extractor, intent_resolver, NLU-aware FSM."""

from __future__ import annotations

import pytest

from nlu.slot_extractor import extract_slots
from nlu.intent_resolver import (
    NluResult,
    _infer_from_context,
    _score_to_tier,
    CONFIDENT_THRESHOLD,
    CLARIFY_THRESHOLD,
)
from nlu.store import IntentMatch, get_fillers, get_reprompts, _FILLER_FALLBACKS
from runtime.executor import _advance_past_filled_steps
from runtime.session import SessionState


# ── slot_extractor ────────────────────────────────────────────────────────────

class TestExtractSlots:
    def test_multi_slot_single_utterance(self):
        slots = extract_slots("tôi tên Nguyễn Văn A, khám tim mạch ngày mai buổi sáng 9 giờ")
        assert slots["patient_name"] == "Nguyễn Văn A"
        assert slots["specialty"] == "Tim mạch"
        assert "appointment_date" in slots
        assert slots["time_of_day"] == "sáng"
        assert slots["appointment_hour"] == "9"

    def test_date_tomorrow(self):
        slots = extract_slots("muốn đặt ngày mai")
        assert "appointment_date" in slots

    def test_date_today(self):
        slots = extract_slots("khám hôm nay")
        assert "appointment_date" in slots

    def test_weekday(self):
        slots = extract_slots("đặt thứ Sáu")
        assert "appointment_date" in slots

    def test_date_ngay_mot_is_plus_two_days(self):
        from datetime import datetime, timedelta  # noqa: PLC0415
        slots = extract_slots("đặt ngày mốt")
        expected = (datetime.now() + timedelta(days=2)).strftime("%d/%m/%Y")
        assert expected in slots["appointment_date"]

    def test_date_ngay_kia_is_plus_three_days_not_two(self):
        """Real bug found via manual Portal Simulator testing: "ngày kia"
        was wrongly treated as a synonym of "ngày mốt" (both +2). The
        Vietnamese sequential idiom is hôm nay(+0)/mai(+1)/mốt(+2)/kia(+3)/
        kìa(+4) — "ngày kia" must resolve one day later than "ngày mốt"."""
        from datetime import datetime, timedelta  # noqa: PLC0415
        slots = extract_slots("đặt ngày kia")
        expected = (datetime.now() + timedelta(days=3)).strftime("%d/%m/%Y")
        wrong = (datetime.now() + timedelta(days=2)).strftime("%d/%m/%Y")
        assert expected in slots["appointment_date"]
        assert wrong not in slots["appointment_date"]

    def test_date_ngay_kia_vs_ngay_kia_not_conflated(self):
        """Real bug found via a 95-call batch test: my own first fix for
        "ngày kia" accidentally grouped "ngày kìa" into the SAME +3 branch —
        they must resolve to different dates (+3 vs +4)."""
        from datetime import datetime, timedelta  # noqa: PLC0415
        kia = extract_slots("đặt ngày kia")["appointment_date"]
        kia_expected = (datetime.now() + timedelta(days=3)).strftime("%d/%m/%Y")
        assert kia_expected in kia

        kia_dau = extract_slots("đặt ngày kìa")["appointment_date"]
        kia_dau_expected = (datetime.now() + timedelta(days=4)).strftime("%d/%m/%Y")
        assert kia_dau_expected in kia_dau
        assert kia != kia_dau

    def test_date_counting_words_n_hom_nua(self):
        """"ba hôm nữa"/"bốn hôm nữa" etc. handled directly by regex instead
        of relying on the LLM slot-recovery path to guess the mapping —
        found via batch test: the LLM had no "+4" keyword to reach for and
        silently mapped "bốn hôm nữa" onto the same (wrong) date as "ba hôm
        nữa"."""
        from datetime import datetime, timedelta  # noqa: PLC0415
        for word, offset in [("hai", 2), ("ba", 3), ("bốn", 4), ("năm", 5)]:
            slots = extract_slots(f"đặt {word} hôm nữa")
            expected = (datetime.now() + timedelta(days=offset)).strftime("%d/%m/%Y")
            assert expected in slots["appointment_date"], f"{word} hôm nữa should be +{offset} days"

    def test_date_counting_digits_n_ngay_nua(self):
        """Digit form of the same idiom ("còn 2 ngày nữa") — real bug found
        by an automated date-correctness check over a 95-call batch: this
        fell through the word-form branch straight to the LLM, which
        guessed +3 instead of +2 with no exact keyword to anchor on."""
        from datetime import datetime, timedelta  # noqa: PLC0415
        for n in (2, 3, 4, 5):
            slots = extract_slots(f"còn {n} ngày nữa")
            expected = (datetime.now() + timedelta(days=n)).strftime("%d/%m/%Y")
            assert expected in slots["appointment_date"], f"{n} ngày nữa should be +{n} days"

    def test_date_weekday_next_week_compound(self):
        """"thứ Ba tuần sau" — a caller-LLM dynamic conversation test caught
        the plain "tuần sau" branch (today+7 raw calendar days, checked
        before the weekday loop) winning over the named weekday whenever
        both appeared together, landing on the wrong day of week entirely
        (e.g. today Saturday + "thứ Ba tuần sau" resolved to next Saturday
        instead of next Tuesday)."""
        from datetime import datetime, timedelta  # noqa: PLC0415
        now = datetime.now()
        this_monday = now - timedelta(days=now.weekday())
        next_monday = this_monday + timedelta(days=7)
        for word, target_wd in [("thứ Hai", 0), ("thứ Ba", 1), ("thứ Tư", 2), ("thứ Bảy", 5)]:
            slots = extract_slots(f"em muốn đặt {word} tuần sau")
            expected_dt = next_monday + timedelta(days=target_wd)
            expected = expected_dt.strftime("%d/%m/%Y")
            assert expected in slots["appointment_date"], f"{word} tuần sau should land on next week's {word}"
            assert expected_dt.weekday() == target_wd

    def test_phone(self):
        slots = extract_slots("số điện thoại của tôi là 0901234567")
        assert slots["patient_phone"] == "0901234567"

    def test_specialty_long_phrase_priority(self):
        slots = extract_slots("muốn khám nội soi tiêu hóa")
        assert slots["specialty"] == "Nội soi - Tiêu hóa"

    def test_symptom_implies_specialty(self):
        slots = extract_slots("bị đau lưng dưới mấy hôm nay")
        assert slots["specialty"] == "Xương khớp"
        assert "symptom_description" in slots

    def test_no_slots_when_utterance_empty(self):
        slots = extract_slots("")
        assert slots == {}

    def test_name_stops_at_comma(self):
        slots = extract_slots("tên là Trần Thị Mai, khám ngày mai")
        assert slots["patient_name"] == "Trần Thị Mai"

    def test_time_slot_derived(self):
        slots = extract_slots("buổi chiều 14 giờ")
        assert slots["time_slot"] == "buổi chiều lúc 14 giờ"

    def test_noisoi_combo(self):
        slots = extract_slots("nội soi cả dạ dày và đại tràng")
        assert slots["noisoi_type"] == "combo"

    def test_noisoi_dai_trang(self):
        slots = extract_slots("nội soi đại tràng thôi")
        assert slots["noisoi_type"] == "dai_trang"

    def test_time_inferred_from_hour(self):
        slots = extract_slots("đặt lúc 15 giờ")
        assert slots["time_of_day"] == "chiều"


# ── intent_resolver helpers ───────────────────────────────────────────────────

class TestScoreToTier:
    def test_confident(self):
        assert _score_to_tier(CONFIDENT_THRESHOLD) == "confident"
        assert _score_to_tier(0.95) == "confident"

    def test_clarify(self):
        assert _score_to_tier(CLARIFY_THRESHOLD) == "clarify"
        assert _score_to_tier((CONFIDENT_THRESHOLD + CLARIFY_THRESHOLD) / 2) == "clarify"

    def test_handoff(self):
        assert _score_to_tier(0.0) == "handoff"
        assert _score_to_tier(CLARIFY_THRESHOLD - 0.01) == "handoff"


class TestInferFromContext:
    def test_booking_markers(self):
        assert _infer_from_context("muốn đặt lịch khám", {}) == "book_appointment"

    def test_symptom_markers(self):
        assert _infer_from_context("bị đau đầu mấy hôm nay", {}) == "symptom_described"

    def test_inquiry_markers(self):
        assert _infer_from_context("giá khám bao nhiêu", {}) == "service_inquiry"

    def test_specialty_slot_fallback(self):
        assert _infer_from_context("tim mạch", {"specialty": "Tim mạch"}) == "book_appointment"

    def test_no_signal(self):
        assert _infer_from_context("à ừm", {}) is None


# ── NLU store helpers ─────────────────────────────────────────────────────────

class TestNluStore:
    def test_get_fillers_fallback_when_store_empty(self):
        # Store is empty in tests — should return hardcoded fallbacks
        fillers = get_fillers("thinking")
        assert isinstance(fillers, list)
        assert len(fillers) > 0
        assert all(isinstance(f, str) for f in fillers)

    def test_get_fillers_unknown_context_returns_default(self):
        fillers = get_fillers("nonexistent_context")
        assert fillers == ["Dạ,"]

    def test_get_reprompts_empty_store(self):
        reprompts = get_reprompts("collect_specialty", script_id="fake")
        assert reprompts == []

    def test_intent_match_dataclass(self):
        m = IntentMatch(intent="book_appointment", score=0.87, preset_slots={"specialty": "Tim mạch"})
        assert m.intent == "book_appointment"
        assert m.score == 0.87
        assert m.preset_slots["specialty"] == "Tim mạch"


# ── FSM multi-slot skip ───────────────────────────────────────────────────────

class TestAdvancePastFilledSteps:
    def _make_steps(self) -> dict:
        return {
            "collect_specialty": {
                "id": "collect_specialty",
                "type": "speak_listen",
                "transitions": [{"when": "slot.specialty != null", "goto": "collect_name"}],
            },
            "collect_name": {
                "id": "collect_name",
                "type": "speak_listen",
                "transitions": [{"when": "slot.patient_name != null", "goto": "collect_date"}],
            },
            "collect_date": {
                "id": "collect_date",
                "type": "speak_listen",
                "transitions": [{"when": "slot.appointment_date != null", "goto": "confirm"}],
            },
            "confirm": {"id": "confirm", "type": "speak"},
        }

    def _state(self, step_id: str, slots: dict) -> SessionState:
        return SessionState(
            session_id="s1", script_id="sc1",
            current_step_id=step_id, slots=slots,
        )

    def test_skips_all_three_filled(self):
        slots = {"specialty": "Tim mạch", "patient_name": "Nguyễn Văn A", "appointment_date": "thứ Sáu"}
        state = self._state("collect_specialty", slots)
        advanced = _advance_past_filled_steps(state, self._make_steps())
        assert advanced.current_step_id == "confirm"

    def test_stops_at_unfilled(self):
        slots = {"specialty": "Tim mạch"}  # name and date missing
        state = self._state("collect_specialty", slots)
        advanced = _advance_past_filled_steps(state, self._make_steps())
        assert advanced.current_step_id == "collect_name"

    def test_no_advance_when_nothing_filled(self):
        state = self._state("collect_specialty", {})
        advanced = _advance_past_filled_steps(state, self._make_steps())
        assert advanced.current_step_id == "collect_specialty"

    def test_stops_at_terminal_step(self):
        slots = {"specialty": "X", "patient_name": "Y", "appointment_date": "Z"}
        state = self._state("confirm", slots)
        advanced = _advance_past_filled_steps(state, self._make_steps())
        assert advanced.current_step_id == "confirm"

    def test_skips_two_of_three(self):
        slots = {"specialty": "Tim mạch", "patient_name": "Nguyễn Văn A"}
        state = self._state("collect_specialty", slots)
        advanced = _advance_past_filled_steps(state, self._make_steps())
        assert advanced.current_step_id == "collect_date"
