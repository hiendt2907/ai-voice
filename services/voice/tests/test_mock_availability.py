"""Tests for the mock-availability slot-fill and stale-time-clear helpers in
runtime/executor.py.

Covers two bugs found via real-call testing on GCP:

1. collect_date used to send the caller to collect_time (ask for an exact
   hour) whenever only a date was given. Real front-desk behavior is the
   opposite — check what's open, don't make the caller guess. There's no
   merchant-calendar API yet, so confirm_time_available now gets a mock
   slot auto-assigned when time_slot is still empty on arrival.

2. When the caller denies the offered time without giving a new one in the
   same utterance ("không được, đổi giờ khác giúp tôi"), the OLD time_slot
   was never cleared — the multi-slot-skip in async_process_turn immediately
   bounced collect_time back to confirm_time_available and re-read the same
   rejected offer verbatim instead of asking again.
"""

from __future__ import annotations

from runtime.executor import _clear_stale_time_on_rejection, _fill_time_slot_if_landing_unset
from runtime.session import SessionState


def _state(**slots: str) -> SessionState:
    return SessionState(
        session_id="s1", script_id="test-script", current_step_id="x", slots=slots
    )


class TestFillTimeSlotIfLandingUnset:
    def test_fills_when_landing_on_confirm_with_no_time(self):
        state = _state(appointment_date="21/08/2026")
        result = _fill_time_slot_if_landing_unset(state, "confirm_time_available")
        assert result.slots.get("time_slot")
        assert result.slots.get("appointment_hour")
        assert result.slots.get("time_of_day") in ("sáng", "chiều")

    def test_does_not_override_existing_time_slot(self):
        state = _state(appointment_date="21/08/2026", time_slot="buổi sáng lúc 9:00 giờ")
        result = _fill_time_slot_if_landing_unset(state, "confirm_time_available")
        assert result.slots["time_slot"] == "buổi sáng lúc 9:00 giờ"

    def test_noop_for_other_steps(self):
        state = _state(appointment_date="21/08/2026")
        result = _fill_time_slot_if_landing_unset(state, "collect_time")
        assert "time_slot" not in result.slots


class TestClearStaleTimeOnRejection:
    def test_clears_old_time_on_bare_deny(self):
        state = _state(time_slot="buổi sáng lúc 10:00 giờ", appointment_hour="10:00", time_of_day="sáng")
        result = _clear_stale_time_on_rejection(state, "collect_time", "deny", new_slots={})
        assert "time_slot" not in result.slots
        assert "appointment_hour" not in result.slots
        assert "time_of_day" not in result.slots

    def test_clears_old_time_on_change_time_intent(self):
        state = _state(time_slot="buổi sáng lúc 10:00 giờ", appointment_hour="10:00", time_of_day="sáng")
        result = _clear_stale_time_on_rejection(state, "collect_time", "change_time", new_slots={})
        assert "time_slot" not in result.slots

    def test_applies_fresh_full_time_given_in_same_utterance(self):
        """"không, đổi sang 3 giờ chiều" — the new preference must survive
        (and fully replace the old one), not get silently kept as the old
        9:30 alongside a half-updated day-part."""
        state = _state(time_slot="buổi sáng lúc 10:00 giờ", appointment_hour="10:00", time_of_day="sáng")
        result = _clear_stale_time_on_rejection(
            state, "collect_time", "change_time", new_slots={"time_of_day": "chiều", "appointment_hour": "15"}
        )
        assert result.slots.get("time_of_day") == "chiều"
        assert result.slots.get("appointment_hour") == "15"
        assert result.slots.get("time_slot") == "buổi chiều lúc 15 giờ"

    def test_partial_new_time_of_day_drops_stale_hour(self):
        """Real bug found via 114-call batch test: caller says just "buổi
        sáng" (no hour) after the offered "9:30" — the OLD hour must not
        survive and recombine into the same offer as before, or the flow
        bounces straight back to confirm_time_available repeating the exact
        same rejected text verbatim."""
        state = _state(time_slot="buổi sáng lúc 9:30 giờ", appointment_hour="9:30", time_of_day="sáng")
        result = _clear_stale_time_on_rejection(
            state, "collect_time", "change_time", new_slots={"time_of_day": "sáng"}
        )
        assert "appointment_hour" not in result.slots
        assert result.slots.get("time_slot") == "buổi sáng"

    def test_noop_for_confirm_intent(self):
        state = _state(time_slot="buổi sáng lúc 10:00 giờ")
        result = _clear_stale_time_on_rejection(state, "collect_patient_info", "confirm", new_slots={})
        assert result.slots["time_slot"] == "buổi sáng lúc 10:00 giờ"
