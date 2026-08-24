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
from runtime.executor import _advance_past_filled_steps, process_turn
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

    def test_date_weekday_digit_form_next_week(self):
        """Người Việt nói thứ bằng SỐ rất phổ biến ("thứ 3", "thứ 6") không
        kém gì dạng chữ. Trước đây _WEEKDAY_PATTERNS chỉ khớp dạng chữ cho
        thứ 2-6 (chỉ riêng thứ Bảy có alias số) nên "thứ 3 tuần sau" không
        khớp pattern nào, rơi xuống nhánh fallback "_has_next_week" luôn
        chốt hôm nay+7 ngày bất kể khách nói thứ mấy. Tái hiện từ 2 transcript
        thật (persona 74, 91 của batch test 100 cuộc): 'sáng thứ 3 tuần sau'
        và 'sáng thứ 6 tuần sau' từng cho CÙNG một kết quả sai "thứ Hai"."""
        from datetime import datetime, timedelta  # noqa: PLC0415
        now = datetime.now()
        this_monday = now - timedelta(days=now.weekday())
        next_monday = this_monday + timedelta(days=7)
        for digit, target_wd in [("2", 0), ("3", 1), ("4", 2), ("5", 3), ("6", 4)]:
            slots = extract_slots(f"em muốn đặt thứ {digit} tuần sau")
            expected_dt = next_monday + timedelta(days=target_wd)
            expected = expected_dt.strftime("%d/%m/%Y")
            assert expected in slots["appointment_date"], (
                f"thứ {digit} tuần sau should land on next week's thứ {digit}"
            )
            assert expected_dt.weekday() == target_wd

    def test_date_weekday_digit_form_without_next_week(self):
        """Dạng số không kèm "tuần sau" phải resolve ra thứ đó GẦN NHẤT sắp
        tới (giống hệt cách dạng chữ đã hoạt động), không phải hôm nay+7."""
        from datetime import datetime, timedelta  # noqa: PLC0415
        now = datetime.now()
        for digit, target_wd in [("2", 0), ("3", 1), ("4", 2), ("5", 3), ("6", 4)]:
            slots = extract_slots(f"em muốn đặt thứ {digit}")
            days_ahead = (target_wd - now.weekday()) % 7 or 7
            expected = (now + timedelta(days=days_ahead)).strftime("%d/%m/%Y")
            assert expected in slots["appointment_date"], (
                f"thứ {digit} should land on the nearest upcoming thứ {digit}"
            )

    def test_date_digit_weekday_not_confused_with_calendar_date(self):
        """Nhập nhằng cần tránh: "3 tháng 9" (ngày 3 tháng 9) không có chữ
        "thứ" đứng ngay trước số 3, nên KHÔNG được hiểu nhầm thành "thứ 3".
        Pattern \\bthứ\\s*3\\b neo chữ "thứ" ngay trước số nên câu này phải
        rơi xuống nhánh parse ngày/tháng bên dưới, ra đúng 03/09."""
        slots = extract_slots("cho tôi đặt lịch ngày 3 tháng 9")
        assert "appointment_date" in slots
        assert "03/09" in slots["appointment_date"]

    def test_date_weekday_digit_persona_91_thu_sau_tuan_sau(self):
        """Tái hiện đúng transcript thật (persona 91, batch test 100 cuộc):
        khách nói thứ Sáu tuần sau bằng dạng số, phải ra đúng thứ Sáu của
        tuần sau — không phải thứ Hai (kết quả sai trước khi sửa)."""
        from datetime import datetime, timedelta  # noqa: PLC0415
        now = datetime.now()
        this_monday = now - timedelta(days=now.weekday())
        next_monday = this_monday + timedelta(days=7)
        expected_friday = (next_monday + timedelta(days=4)).strftime("%d/%m/%Y")
        wrong_monday = (next_monday + timedelta(days=0)).strftime("%d/%m/%Y")

        slots = extract_slots("tui đặt vào sáng thứ 6 tuần sau, 9 giờ đúng không?")
        assert expected_friday in slots["appointment_date"]
        assert wrong_monday not in slots["appointment_date"]
        assert slots["appointment_hour"] == "9"

    def test_hour_prefers_last_anchored_over_incidental_earlier_number(self):
        """A dynamic LLM-caller test caught the old single re.search grabbing
        the leftmost hour-like number in the utterance even when it was an
        incidental aside (clinic closing time), not the customer's actual
        requested hour stated later with an explicit "lúc" anchor:
        "Chủ nhật chỉ làm đến 12 giờ thôi hả? ... tôi đặt lịch thứ Hai lúc 8
        giờ sáng nhé" must extract hour=8, not hour=12."""
        slots = extract_slots(
            "Thế à, Chủ nhật thì chỉ làm đến 12 giờ thôi hả? Tôi định đi buổi "
            "sáng sớm chút mà nghe hơi gấp. Thôi được rồi, vậy tôi đặt lịch "
            "thứ Hai lúc 8 giờ sáng nhé, nhưng nhớ nhắc kỹ là tôi hay bị trễ "
            "giờ một tí đấy."
        )
        assert slots["appointment_hour"] == "8"

    def test_hour_falls_back_to_last_bare_mention_without_anchor(self):
        slots = extract_slots("9 giờ hay 10 giờ đều được, thôi 10 giờ nhé")
        assert slots["appointment_hour"] == "10"

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

    # ── "tối đa"/"tối thiểu" must not be read as buổi tối ──────────────────

    def test_toi_da_not_read_as_evening(self):
        """Real bug found from a production transcript: a caller asked
        "mỗi buổi khám có tối đa bao nhiêu người ạ?" in the middle of a
        morning booking, and \\btối\\b matched the "tối" inside "tối đa"
        (word-boundary only checks around "tối", not the following word),
        overwriting time_of_day with "tối" and making the AI confirm the
        wrong buổi entirely."""
        slots = extract_slots("cho tôi hỏi tối đa bao nhiêu người")
        assert "time_of_day" not in slots

    def test_toi_thieu_not_read_as_evening(self):
        slots = extract_slots("tối thiểu bao nhiêu tuổi thì khám được")
        assert "time_of_day" not in slots

    def test_toi_da_does_not_override_earlier_sang(self):
        """The exact production shape: buổi sáng stated first, "tối đa"
        aside stated later in the SAME utterance — sáng must win, not be
        clobbered by the false "tối" match."""
        slots = extract_slots("đặt buổi sáng 10 giờ, mà tối đa bao nhiêu người một buổi vậy em")
        assert slots["time_of_day"] == "sáng"

    def test_buoi_toi_still_matches(self):
        """Negative-lookahead guard must not break the real "buổi tối" case
        it was carved out of."""
        slots = extract_slots("đặt lịch buổi tối nhé")
        assert slots["time_of_day"] == "tối"

    def test_gio_toi_still_matches(self):
        slots = extract_slots("7 giờ tối")
        assert slots["time_of_day"] == "tối"
        assert slots["appointment_hour"] == "7"

    # ── "rưỡi" (half past) hour parsing ─────────────────────────────────────

    def test_bare_n_ruoi_sang(self):
        """"7 rưỡi sáng" (no "giờ") used to be invisible to the hour regex
        entirely — real bug: a caller said this twice and the AI never
        picked up an appointment_hour at all."""
        slots = extract_slots("đặt cho tôi 7 rưỡi sáng nhé")
        assert slots["appointment_hour"] == "7:30"
        assert slots["time_of_day"] == "sáng"

    def test_n_gio_ruoi_sang(self):
        """"8 giờ rưỡi sáng" used to match the plain "giờ" branch first and
        silently round down to a bare "8", losing the half hour."""
        slots = extract_slots("đặt lúc 8 giờ rưỡi sáng")
        assert slots["appointment_hour"] == "8:30"

    def test_ruoi_chieu_and_toi(self):
        # AM/PM correction (pre-existing behaviour) applies to the half-hour
        # branch too: "3 rưỡi chiều" → 15:30, not 3:30.
        slots = extract_slots("3 rưỡi chiều")
        assert slots["appointment_hour"] == "15:30"
        # "tối" only shifts 1-5 under the existing AM/PM rule (unchanged by
        # this fix) — 7 stays 7, matching "7 giờ tối" today.
        slots = extract_slots("khám lúc 7 giờ rưỡi tối")
        assert slots["appointment_hour"] == "7:30"

    def test_ruoi_time_slot_rendering(self):
        slots = extract_slots("7 rưỡi sáng")
        assert slots["time_slot"] == "buổi sáng lúc 7 giờ 30"

    def test_plain_hour_regression_after_ruoi_support(self):
        """No-"rưỡi" hour extraction (existing behaviour) must keep working
        unchanged after adding the "rưỡi" branch."""
        slots = extract_slots("đặt lúc 9 giờ sáng")
        assert slots["appointment_hour"] == "9"
        slots = extract_slots("9 giờ hay 10 giờ đều được, thôi 10 giờ nhé")
        assert slots["appointment_hour"] == "10"

    def test_ruoi_money_not_read_as_hour(self):
        """"7 rưỡi triệu" (7.5 million VND) is a price, not a time — must
        not be captured as an hour."""
        slots = extract_slots("chi phí khoảng 7 rưỡi triệu thôi ạ")
        assert "appointment_hour" not in slots


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


# ── confirm_time_available must reflect what the caller actually said ─────────
#
# Real production transcripts (persona 97 và persona 99): khách nói rõ "buổi
# tối" + "7 rưỡi" nhiều lần, nhưng AI xác nhận lại "buổi tối lúc 8 giờ" —
# tổng hợp của lỗi 1 ("tối đa" bị hiểu nhầm) và lỗi 2 (không hỗ trợ "rưỡi").
# Các test dưới đây kiểm tra ở TẦNG EXTRACTOR/EXECUTOR: state.slots phải
# phản ánh đúng nguyên văn khách nói khi landing ở confirm_time_available —
# bất kể _MOCK_AVAILABLE_HOURS có khung đó hay không (đây không phải test
# "có đặt được lịch không", chỉ là test dữ liệu được trích xuất đúng).

class TestConfirmTimeAvailableReflectsCallerStatedTime:
    def _script(self) -> dict:
        return {
            "id": "test-script",
            "entry_step": "collect_time",
            "steps": [
                {
                    "id": "collect_time",
                    "type": "speak_listen",
                    "variants": [{"id": "v1", "beats": [{"text": "Anh chị muốn giờ nào ạ?"}]}],
                    "transitions": [{"when": "slot.time_slot != null", "goto": "confirm_time_available"}],
                    "fallback_goto": "handoff_to_staff",
                    "max_no_match": 3,
                },
                {
                    "id": "confirm_time_available",
                    "type": "speak_listen",
                    "variants": [{"id": "v1", "beats": [{"text": "Dạ để em kiểm tra giờ {{time_slot}} ạ."}]}],
                    "transitions": [{"when": "true", "goto": "done"}],
                },
                {"id": "handoff_to_staff", "type": "handoff"},
                {"id": "done", "type": "speak"},
            ],
        }

    def _state(self) -> SessionState:
        return SessionState(session_id="s1", script_id="test-script", current_step_id="collect_time", slots={})

    def test_persona_97_evening_half_past_seven(self):
        """Nguyên văn persona 97: 'Em ơi, chị chọn buổi tối ấy. 7 rưỡi nha.
        Thế Chủ nhật 30/8, 7 rưỡi em đặt cho chị nhé.' — phải chốt đúng
        buổi tối + 7:30, KHÔNG bị mock ghi đè thành giờ khác."""
        state = self._state()
        result = process_turn(
            state, self._script(),
            "Em ơi, chị chọn buổi tối ấy. 7 rưỡi nha. Thế Chủ nhật 30/8, 7 rưỡi em đặt cho chị nhé.",
        )
        assert result.next_step_id == "confirm_time_available"
        assert result.state.slots["time_of_day"] == "tối"
        assert result.state.slots["appointment_hour"] == "7:30"
        assert result.state.slots["time_slot"] == "buổi tối lúc 7 giờ 30"

    def test_persona_99_evening_half_past_seven_variant(self):
        """Nguyên văn kiểu persona 99: khách nói buổi tối và giờ rưỡi trong
        cùng một câu, không có mốc "lúc" neo."""
        state = self._state()
        result = process_turn(state, self._script(), "Cho tôi đặt 7 rưỡi tối được không em")
        assert result.state.slots["time_of_day"] == "tối"
        assert result.state.slots["appointment_hour"] == "7:30"

    def test_toi_da_aside_does_not_flip_morning_booking(self):
        """Câu hỏi phụ 'tối đa bao nhiêu người' xen giữa một cuộc đặt lịch
        buổi sáng không được làm lật time_of_day sang tối."""
        state = self._state()
        result = process_turn(
            state, self._script(),
            "Đặt cho tôi 10 giờ sáng, à mà mỗi buổi khám có tối đa bao nhiêu người ạ?",
        )
        assert result.state.slots["time_of_day"] == "sáng"
        assert result.state.slots["appointment_hour"] == "10"

    def test_mock_never_overrides_when_time_already_extracted(self):
        """_fill_time_slot_if_landing_unset chỉ được phép mock-pick khi
        time_slot THẬT SỰ trống — không bao giờ ghi đè giờ đã trích được từ
        chính utterance này."""
        state = self._state()
        result = process_turn(state, self._script(), "buổi tối 7 rưỡi")
        picked_hour = result.state.slots["appointment_hour"]
        assert picked_hour == "7:30"
        # 7:30 tối is not in the sáng/chiều-only mock pool — proves this
        # value came from extraction, not from _mock_pick_available_slot.
        from runtime.executor import _MOCK_AVAILABLE_HOURS  # noqa: PLC0415
        assert picked_hour not in _MOCK_AVAILABLE_HOURS

    def test_mock_still_fills_when_caller_gave_no_time_at_all(self):
        """Ngược lại: khi khách hoàn toàn không nói giờ, mock vẫn phải được
        phép điền — đây KHÔNG phải hành vi bị coi là lỗi."""
        state = self._state()
        result = process_turn(state, self._script(), "dạ vâng anh chị ơi cứ sắp cho tôi giờ nào cũng được")
        # No time_of_day/appointment_hour extracted from that utterance, so
        # this turn stays on collect_time (transition needs slot.time_slot).
        assert result.next_step_id is None
        assert "appointment_hour" not in result.state.slots
