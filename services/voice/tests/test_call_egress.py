"""Unit tests for call.egress.EgressSender (wire-out primitives)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from call.egress import EgressSender
from call.events import BeatPayload


class _FakeAdapter:
    """Identity adapter — encode_outbound returns [payload] unchanged."""

    name = "fake"

    def encode_outbound(self, payload):  # noqa: ANN001
        return [payload]

    async def on_call_end(self, reason, session_id):  # noqa: ANN001
        pass


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, msg) -> None:  # noqa: ANN001
        self.sent.append(msg)


@pytest.mark.asyncio
async def test_send_encodes_via_adapter_and_sends_each_message():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    await egress.send({"event": "beat", "text": "hi"})

    assert ws.sent == [{"event": "beat", "text": "hi"}]


@pytest.mark.asyncio
async def test_send_beat_dispatches_the_beat_payload():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    await egress.send_beat(BeatPayload(text="xin chào", pause_ms=100, turn=1, step_id="s1"))

    assert len(ws.sent) == 1
    assert ws.sent[0]["text"] == "xin chào"


@pytest.mark.asyncio
async def test_send_audio_base64_encodes_pcm():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    await egress.send_audio(b"\x00\x01\x02\x03", turn=2)

    assert len(ws.sent) == 1
    assert ws.sent[0]["event"] == "audio_chunk"
    assert ws.sent[0]["turn"] == 2
    assert ws.sent[0]["data"]  # non-empty base64 string


@pytest.mark.asyncio
async def test_say_sends_beat_then_synthesizes_via_tts_chain():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]
    tts_chain = AsyncMock()
    tts_chain.synthesize = AsyncMock(return_value=b"\x01\x02")

    await egress.say("xin chào", 1, 0.0, "step1", tts_chain, None)

    beat_msgs = [m for m in ws.sent if m.get("text") == "xin chào"]
    assert len(beat_msgs) == 1
    audio_msgs = [m for m in ws.sent if "data" in m and m.get("text") is None]
    assert len(audio_msgs) == 1
    tts_chain.synthesize.assert_awaited_once()


@pytest.mark.asyncio
async def test_say_falls_back_to_legacy_tts_when_no_chain():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]
    legacy_tts = AsyncMock()
    legacy_tts.synthesize = AsyncMock(return_value=b"\x01")

    await egress.say("hi", 1, 0.0, "step1", None, legacy_tts)

    legacy_tts.synthesize.assert_awaited_once()


@pytest.mark.asyncio
async def test_say_beat_only_when_no_tts_at_all():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    await egress.say("hi", 1, 0.0, "step1", None, None)

    assert len(ws.sent) == 1  # only the text beat, no audio chunk


@pytest.mark.asyncio
async def test_say_swallows_synthesis_errors_and_still_sends_beat():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]
    broken_chain = AsyncMock()
    broken_chain.synthesize = AsyncMock(side_effect=RuntimeError("engine down"))

    await egress.say("hi", 1, 0.0, "step1", broken_chain, None)  # must not raise

    assert len(ws.sent) == 1  # beat still sent, no audio chunk on failure


@pytest.mark.asyncio
async def test_emit_filler_prefers_pre_recorded_audio():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    await egress.emit_filler("um", b"\x01\x02", 1, 0.0, "step1", None, None)

    assert len(ws.sent) == 1
    assert "data" in ws.sent[0]


@pytest.mark.asyncio
async def test_emit_filler_noop_when_no_text_and_no_pcm():
    ws = _FakeWS()
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    await egress.emit_filler("", None, 1, 0.0, "step1", None, None)

    assert ws.sent == []
