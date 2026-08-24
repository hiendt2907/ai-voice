"""Unit tests for call.egress.EgressSender (wire-out primitives)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect, WebSocketState

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


class _StatefulFakeWS:
    """Fake WS that exposes `application_state` like a real Starlette
    WebSocket, so tests can simulate the client hanging up mid-send —
    the race condition this module's send() guards against."""

    def __init__(self, application_state: WebSocketState = WebSocketState.CONNECTED) -> None:
        self.sent: list[dict] = []
        self.application_state = application_state

    async def send_json(self, msg) -> None:  # noqa: ANN001
        self.sent.append(msg)


class _CloseRaceFakeWS:
    """Fake WS that still reports CONNECTED when checked, but raises the
    exact Starlette RuntimeError on the N-th send — reproducing the narrow
    check-then-act race where the client disconnects between the state
    check and the actual ASGI send."""

    def __init__(self, raise_on_call: int, message: str) -> None:
        self.sent: list[dict] = []
        self.application_state = WebSocketState.CONNECTED
        self._raise_on_call = raise_on_call
        self._message = message
        self._calls = 0

    async def send_json(self, msg) -> None:  # noqa: ANN001
        self._calls += 1
        if self._calls == self._raise_on_call:
            raise RuntimeError(self._message)
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


# ── race condition: "Cannot call send once a close message has been sent" ──
# Khách cúp máy (WebSocket đóng) đúng lúc EgressSender đang gửi — trước đây
# self.ws.send_json() ném RuntimeError không được bắt, gây exception rác
# trong log production. Các test dưới đây xác nhận cách sửa: kiểm tra
# `application_state` TRƯỚC khi gửi (đường đi chính), và bắt đúng thông
# điệp lỗi cụ thể của Starlette làm lưới đỡ cho khe hở đua còn lại.


@pytest.mark.asyncio
async def test_send_skips_silently_when_ws_already_disconnected():
    ws = _StatefulFakeWS(application_state=WebSocketState.DISCONNECTED)
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    sent = await egress.send({"event": "beat", "text": "hi"})

    assert sent is False
    assert ws.sent == []  # never attempted the doomed send_json call


@pytest.mark.asyncio
async def test_send_beat_and_send_audio_return_false_when_ws_disconnected():
    ws = _StatefulFakeWS(application_state=WebSocketState.DISCONNECTED)
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    assert await egress.send_beat(BeatPayload(text="hi", pause_ms=0, turn=1, step_id="s1")) is False
    assert await egress.send_audio(b"\x00\x01", turn=1) is False
    assert ws.sent == []
    assert egress.is_playing is False  # playback clock must not advance for undelivered audio


@pytest.mark.asyncio
async def test_send_swallows_exact_close_race_message_and_returns_false():
    """The check-then-act race: application_state still reads CONNECTED at
    check time, but the client disconnects before the real send_json call
    lands — Starlette raises this exact RuntimeError. Must be swallowed."""
    ws = _CloseRaceFakeWS(
        raise_on_call=1,
        message='Cannot call "send" once a close message has been sent.',
    )
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    sent = await egress.send({"event": "beat", "text": "hi"})

    assert sent is False


@pytest.mark.asyncio
async def test_send_reraises_unrelated_runtime_errors():
    """Only the exact close-race message is swallowed — any other
    RuntimeError is a real bug and must still propagate."""
    ws = _CloseRaceFakeWS(raise_on_call=1, message="some unrelated runtime error")
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="some unrelated runtime error"):
        await egress.send({"event": "beat", "text": "hi"})


class _DisconnectRaceFakeWS:
    """Cùng khe hở đua như `_CloseRaceFakeWS` nhưng tái hiện đúng dạng thất
    bại quan sát được thật trên production: uvicorn phát hiện
    ClientDisconnected ngay trong send_json và Starlette ném
    `WebSocketDisconnect` thay vì `RuntimeError` — bắt được qua traceback
    thật khi simulator cúp máy giữa lúc `_fsm_rag_intercept` đang nói."""

    def __init__(self, raise_on_call: int) -> None:
        self.sent: list[dict] = []
        self.application_state = WebSocketState.CONNECTED
        self._raise_on_call = raise_on_call
        self._calls = 0

    async def send_json(self, msg) -> None:  # noqa: ANN001
        self._calls += 1
        if self._calls == self._raise_on_call:
            raise WebSocketDisconnect(code=1006)
        self.sent.append(msg)


@pytest.mark.asyncio
async def test_send_swallows_websocket_disconnect_race_and_returns_false():
    """Dạng thứ hai của cùng race — tầng ASGI thấp hơn ném
    WebSocketDisconnect thay vì RuntimeError. Không so khớp message vì bản
    thân loại ngoại lệ này đã nghĩa là socket đã đóng."""
    ws = _DisconnectRaceFakeWS(raise_on_call=1)
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    sent = await egress.send({"event": "beat", "text": "hi"})

    assert sent is False


@pytest.mark.asyncio
async def test_say_skips_tts_synthesis_when_ws_already_disconnected():
    """No point paying for TTS synthesis for a caller who already hung up."""
    ws = _StatefulFakeWS(application_state=WebSocketState.DISCONNECTED)
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]
    tts_chain = AsyncMock()
    tts_chain.synthesize = AsyncMock(return_value=b"\x01\x02")

    await egress.say("xin chào", 1, 0.0, "step1", tts_chain, None)  # must not raise

    tts_chain.synthesize.assert_not_awaited()
    assert ws.sent == []


@pytest.mark.asyncio
async def test_stream_step_text_only_path_stops_early_once_ws_disconnects():
    """`stream_step`'s no-TTS beat loop must not keep hammering send() for
    every remaining beat once the client is gone — it should stop at the
    first closed-connection signal within the same turn."""
    ws = _StatefulFakeWS(application_state=WebSocketState.CONNECTED)
    egress = EgressSender(ws, _FakeAdapter())  # type: ignore[arg-type]

    async def _flip_to_disconnected_after_first_send(msg):  # noqa: ANN001
        ws.sent.append(msg)
        ws.application_state = WebSocketState.DISCONNECTED

    ws.send_json = _flip_to_disconnected_after_first_send  # type: ignore[method-assign]

    step = {
        "variants": [{"beats": [
            {"text": "câu một"}, {"text": "câu hai"}, {"text": "câu ba"},
        ]}]
    }
    started, ended = [], []

    await egress.stream_step(
        step, {}, 0, turn=1, t_start=0.0,
        current_step_id="s1", tts=None, tts_interrupt=asyncio.Event(),
        on_tts_start=lambda: started.append(True), on_tts_end=lambda: ended.append(True),
    )

    assert len(ws.sent) == 1  # stopped after the first beat, not all three
    assert started == [True]
    assert ended == [True]  # on_tts_end() still runs (finally block intact)
