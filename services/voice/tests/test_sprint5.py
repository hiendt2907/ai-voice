"""Tests for Sprint 5: CloudFone protocol, TTS streamer, WS pipeline."""

import asyncio
import time
import pytest

from cloudfone.protocol import (
    BeatPayload,
    HandoffPayload,
    HangupPayload,
    InboundEvent,
    OutboundEvent,
    StartMessage,
    UtteranceMessage,
)
from tts.streamer import stream_step_beats

# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------

def test_start_message_from_dict():
    d = {
        "event": "start",
        "session_id": "sess-001",
        "campaign_id": "camp-abc",
        "script_version_id": "ver-001",
        "direction": "inbound",
        "caller_number": "0901234567",
        "caller_number_masked": "090***567",
    }
    msg = StartMessage.from_dict(d)
    assert msg.session_id == "sess-001"
    assert msg.campaign_id == "camp-abc"
    assert msg.direction == "inbound"
    assert msg.caller_number_masked == "090***567"


def test_utterance_message_from_dict():
    d = {"event": "utterance", "text": "tôi muốn đặt lịch", "confidence": 0.95}
    msg = UtteranceMessage.from_dict(d)
    assert msg.text == "tôi muốn đặt lịch"
    assert msg.confidence == pytest.approx(0.95)


def test_utterance_defaults():
    msg = UtteranceMessage.from_dict({"event": "utterance"})
    assert msg.text == ""
    assert msg.confidence == 1.0


def test_beat_payload_to_dict():
    beat = BeatPayload(text="Xin chào", pause_ms=250, turn=1, step_id="greeting", ttfa_ms=120.5)
    d = beat.to_dict()
    assert d["event"] == OutboundEvent.BEAT
    assert d["text"] == "Xin chào"
    assert d["pause_ms"] == 250
    assert d["ttfa_ms"] == 120.5


def test_beat_payload_no_ttfa():
    beat = BeatPayload(text="Hi", pause_ms=0, turn=2, step_id="farewell")
    d = beat.to_dict()
    assert "ttfa_ms" not in d


def test_handoff_payload_to_dict():
    hp = HandoffPayload(reason="user_request", step_id="handoff_to_staff")
    d = hp.to_dict()
    assert d["event"] == OutboundEvent.HANDOFF
    assert d["reason"] == "user_request"


def test_hangup_payload_to_dict():
    hp = HangupPayload(step_id="farewell")
    d = hp.to_dict()
    assert d["event"] == OutboundEvent.HANGUP
    assert d["step_id"] == "farewell"


def test_inbound_event_values():
    assert InboundEvent.START == "start"
    assert InboundEvent.UTTERANCE == "utterance"
    assert InboundEvent.HANGUP == "hangup"


# ---------------------------------------------------------------------------
# TTS Streamer tests
# ---------------------------------------------------------------------------

STEP_SPEAK_LISTEN = {
    "id": "greeting",
    "type": "speak_listen",
    "variants": [
        {
            "id": "v1",
            "beats": [
                {"text": "Xin chào,", "pause_after": "breath"},
                {"text": "tôi có thể hỗ trợ gì?", "pause_after": "turn"},
            ],
        }
    ],
    "reprompt_variants": [
        {"id": "r1", "beats": [{"text": "Bạn cần hỗ trợ gì?", "pause_after": "turn"}]},
        {"id": "r2", "beats": [{"text": "Tôi vẫn đang nghe.", "pause_after": "turn"}]},
        {"id": "r3", "beats": [{"text": "Tôi chuyển sang nhân viên.", "pause_after": "turn"}]},
    ],
}


async def collect_beats(step, slots=None, no_match=0, turn=1):
    beats = []
    async for beat in stream_step_beats(step, slots or {}, no_match, turn):
        beats.append(beat)
    return beats


def test_streamer_yields_all_beats():
    beats = asyncio.run(collect_beats(STEP_SPEAK_LISTEN))
    assert len(beats) == 2
    assert beats[0].text == "Xin chào,"
    assert beats[1].text == "tôi có thể hỗ trợ gì?"


def test_streamer_pause_ms():
    beats = asyncio.run(collect_beats(STEP_SPEAK_LISTEN))
    assert beats[0].pause_ms == 250  # breath
    assert beats[1].pause_ms == 1000  # turn


def test_streamer_first_beat_has_ttfa():
    beats = asyncio.run(collect_beats(STEP_SPEAK_LISTEN, turn=3))
    assert beats[0].ttfa_ms is not None
    assert beats[0].ttfa_ms >= 0.0
    # Subsequent beats do NOT have ttfa_ms
    assert beats[1].ttfa_ms is None


def test_streamer_reprompt_cycles():
    # no_match=1 → first reprompt (r1)
    beats_r1 = asyncio.run(collect_beats(STEP_SPEAK_LISTEN, no_match=1))
    assert beats_r1[0].text == "Bạn cần hỗ trợ gì?"

    # no_match=2 → second reprompt (r2)
    beats_r2 = asyncio.run(collect_beats(STEP_SPEAK_LISTEN, no_match=2))
    assert beats_r2[0].text == "Tôi vẫn đang nghe."


def test_streamer_slot_template_replaced():
    step = {
        "id": "confirm",
        "type": "speak",
        "variants": [
            {"id": "v1", "beats": [{"text": "Lịch vào {{date}}, buổi {{time_of_day}}.", "pause_after": "medium"}]}
        ],
    }
    beats = asyncio.run(
        collect_beats(step, slots={"date": "ngày 15", "time_of_day": "sáng"})
    )
    assert "ngày 15" in beats[0].text
    assert "sáng" in beats[0].text


def test_streamer_missing_slot_keeps_placeholder():
    step = {
        "id": "confirm",
        "type": "speak",
        "variants": [
            {"id": "v1", "beats": [{"text": "Lịch vào {{date}}.", "pause_after": "long"}]}
        ],
    }
    beats = asyncio.run(collect_beats(step, slots={}))
    assert "{{date}}" in beats[0].text


def test_streamer_empty_step():
    beats = asyncio.run(collect_beats({"id": "empty", "type": "speak", "variants": []}))
    assert beats == []


def test_streamer_step_id_in_payload():
    beats = asyncio.run(collect_beats(STEP_SPEAK_LISTEN))
    assert all(b.step_id == "greeting" for b in beats)


def test_streamer_turn_in_payload():
    beats = asyncio.run(collect_beats(STEP_SPEAK_LISTEN, turn=7))
    assert all(b.turn == 7 for b in beats)
