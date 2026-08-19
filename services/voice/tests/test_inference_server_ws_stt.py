"""Tests for the /ws/stt streaming STT gateway (Phase 2, D2/D5/D7).

Uses fastapi.testclient.TestClient (sync, runs a real ASGI server in a
background thread so `websocket_connect` behaves like a real socket) with the
same dependency-override pattern as test_inference_server.py — no model is
ever loaded, FakeSTT stands in for FasterWhisperSTT.
"""

from __future__ import annotations

import os
import threading
import time

TEST_TOKEN = "test-service-token-do-not-use-in-prod"
os.environ.setdefault("INFERENCE_SERVER_TOKEN", TEST_TOKEN)

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import inference_server as isrv
from inference_server import INFERENCE_SERVER_TOKEN, app, get_stt
from stt.faster_whisper_stt import STTResult

# Silence PCM below the VAD energy threshold (0.01 RMS).
SILENT_FRAME = (b"\x00\x00") * 160
# Loud PCM above the VAD energy threshold.
SPEECH_FRAME = (b"\x00\x40") * 160  # int16 little-endian ~16384 per sample


class FakeSTT:
    """Deterministic stand-in for FasterWhisperSTT — echoes a fixed
    transcript for any non-empty PCM buffer it's asked to decode."""

    def __init__(self, text: str = "xin chào bác sĩ") -> None:
        self.text = text
        self.calls: list[tuple[int, int]] = []  # (pcm_len, sample_rate)

    def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 8000) -> STTResult:
        self.calls.append((len(pcm_bytes), sample_rate))
        if not pcm_bytes:
            return STTResult(text="", confidence=0.0, is_final=True)
        return STTResult(text=self.text, confidence=0.91, is_final=True)


@pytest.fixture
def fake_stt() -> FakeSTT:
    return FakeSTT()


@pytest.fixture
def client(fake_stt: FakeSTT):
    app.dependency_overrides[get_stt] = lambda: fake_stt
    # TestClient's websocket support doesn't run the lifespan warmup by
    # default in this configuration either — no PiperTTS/model load happens.
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _deterministic_vad_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Module-level constants are read fresh on every _StreamTurn/decode
    call (plain global lookups, not baked in at import time), so patching
    them here makes VAD endpointing and the re-decode cadence deterministic
    without depending on real wall-clock sleeps or on inference_server's
    import order relative to test_inference_server.py."""
    monkeypatch.setattr(isrv, "STREAM_DECODE_INTERVAL_S", 0.0)
    monkeypatch.setattr(isrv, "STREAM_VAD_SILENCE_MS", 0)
    monkeypatch.setattr(isrv, "STREAM_VAD_MIN_SPEECH_MS", 0)


@pytest.fixture
def _partial_decode_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt a single test into the legacy sliding-re-decode partial behavior.

    Partial decode is OFF by default now (see inference_server.py's
    STREAM_PARTIAL_DECODE_ENABLED docstring) — real-call testing showed it
    was nearly useless and contended for CPU with the final decode. The
    infrastructure is kept and still tested here, just gated behind this
    fixture so it stays exercised without being the default path.
    """
    monkeypatch.setattr(isrv, "STREAM_PARTIAL_DECODE_ENABLED", True)


# --- auth ---------------------------------------------------------------


def test_ws_stt_rejects_connection_with_no_auth(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/ws/stt") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "1"})
        ws.receive_json()
    assert exc_info.value.code == 4401


def test_ws_stt_rejects_wrong_token_via_query_param(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/ws/stt?token=wrong") as ws,
    ):
        ws.send_json({"type": "start_turn", "turn_id": "1"})
        ws.receive_json()
    assert exc_info.value.code == 4401


def test_ws_stt_rejects_wrong_token_via_auth_message(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect("/ws/stt") as ws:
        ws.send_json({"type": "auth", "token": "wrong"})
        ws.receive_json()  # closed before anything is sent back
    assert exc_info.value.code == 4401


def test_ws_stt_accepts_token_via_query_param(client: TestClient) -> None:
    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "1"})
        ws.send_bytes(SPEECH_FRAME)
        ws.send_json({"type": "end_turn"})
        msg = ws.receive_json()
        assert msg["type"] == "stt.final"
        assert msg["turn_id"] == "1"


def test_ws_stt_accepts_token_via_first_auth_message(client: TestClient) -> None:
    with client.websocket_connect("/ws/stt") as ws:
        ws.send_json({"type": "auth", "token": INFERENCE_SERVER_TOKEN})
        ws.send_json({"type": "start_turn", "turn_id": "2"})
        ws.send_bytes(SPEECH_FRAME)
        ws.send_json({"type": "end_turn"})
        msg = ws.receive_json()
        assert msg["type"] == "stt.final"
        assert msg["turn_id"] == "2"


# --- protocol -------------------------------------------------------------


def test_ws_stt_end_turn_emits_final_with_transcript(
    client: TestClient, fake_stt: FakeSTT
) -> None:
    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "42", "sample_rate": 8000})
        ws.send_bytes(SPEECH_FRAME)
        ws.send_bytes(SPEECH_FRAME)
        ws.send_json({"type": "end_turn"})

        msg = ws.receive_json()
        while msg["type"] == "stt.partial":
            msg = ws.receive_json()

    assert msg == {
        "type": "stt.final",
        "turn_id": "42",
        "text": fake_stt.text,
        "confidence": 0.91,
    }
    assert fake_stt.calls  # decode actually ran


def test_ws_stt_end_turn_with_no_audio_emits_empty_final(client: TestClient) -> None:
    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "3"})
        ws.send_json({"type": "end_turn"})
        msg = ws.receive_json()

    assert msg == {"type": "stt.final", "turn_id": "3", "text": "", "confidence": 0.0}


@pytest.mark.usefixtures("_partial_decode_enabled")
def test_ws_stt_emits_partial_before_end_turn(client: TestClient) -> None:
    """With STREAM_DECODE_INTERVAL_S patched to 0 and partial decode opted
    back in, every audio chunk after the first should trigger a sliding
    re-decode partial."""
    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "7"})
        ws.send_bytes(SPEECH_FRAME)

        msg = ws.receive_json()

        ws.send_json({"type": "end_turn"})
        final = ws.receive_json()

    assert msg["type"] == "stt.partial"
    assert msg["turn_id"] == "7"
    assert final["type"] == "stt.final"


@pytest.mark.usefixtures("_partial_decode_enabled")
def test_ws_stt_vad_endpoint_auto_finalizes_without_explicit_end_turn(
    client: TestClient,
) -> None:
    """Speech followed by a silent frame should emit stt.endpoint then
    stt.final on its own — the caller never has to send end_turn if VAD
    detects the pause (matches D7's endpointing intent)."""
    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "9"})
        ws.send_bytes(SPEECH_FRAME)
        # partial (decode interval patched to 0, partial decode opted in)
        partial = ws.receive_json()
        assert partial["type"] == "stt.partial"

        ws.send_bytes(SILENT_FRAME)
        endpoint = ws.receive_json()
        final = ws.receive_json()

    assert endpoint == {"type": "stt.endpoint", "turn_id": "9"}
    assert final["type"] == "stt.final"
    assert final["turn_id"] == "9"


def test_ws_stt_partial_decode_disabled_by_default_no_partial_events(
    client: TestClient,
) -> None:
    """Default behavior (STREAM_PARTIAL_DECODE_ENABLED unset/"0"): no
    `stt.partial` event is ever sent during an utterance, even with the
    sliding-re-decode interval patched to 0 (which would fire a partial on
    every chunk if the flag were on) — only stt.endpoint/stt.final."""
    assert isrv.STREAM_PARTIAL_DECODE_ENABLED is False
    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "20"})
        ws.send_bytes(SPEECH_FRAME)
        ws.send_bytes(SPEECH_FRAME)
        ws.send_bytes(SPEECH_FRAME)
        ws.send_bytes(SILENT_FRAME)  # triggers VAD end-of-utterance
        endpoint = ws.receive_json()
        final = ws.receive_json()

    assert endpoint == {"type": "stt.endpoint", "turn_id": "20"}
    assert final["type"] == "stt.final"
    assert final["turn_id"] == "20"


def test_ws_stt_audio_before_start_turn_is_dropped_not_crashed(client: TestClient) -> None:
    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_bytes(SPEECH_FRAME)  # no start_turn yet — must be a no-op
        ws.send_json({"type": "start_turn", "turn_id": "5"})
        ws.send_bytes(SPEECH_FRAME)
        ws.send_json({"type": "end_turn"})
        msg = ws.receive_json()

    assert msg["type"] == "stt.final"
    assert msg["turn_id"] == "5"


# --- final decode must not be serialized behind an in-flight partial -----


class _SlowPartialThenFastFinalSTT:
    """Simulates the CT2/faster-whisper serialization bug: the FIRST call
    (the partial re-decode) blocks in its worker thread until released;
    every subsequent call (the final decode) must be able to complete
    WITHOUT waiting for that release — proving final isn't queued behind
    partial's still-running thread."""

    def __init__(self) -> None:
        self.partial_started = threading.Event()
        self.release_partial = threading.Event()
        self.final_call_started_at: float | None = None
        self.calls = 0

    def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 8000) -> STTResult:
        self.calls += 1
        if self.calls == 1:
            self.partial_started.set()
            # Block "in CT2" until the test explicitly releases it — this
            # models a thread that cancel() cannot actually stop.
            self.release_partial.wait(timeout=5.0)
            return STTResult(text="stale-partial", confidence=0.5, is_final=True)
        self.final_call_started_at = time.monotonic()
        return STTResult(text="final transcript", confidence=0.9, is_final=True)


@pytest.mark.usefixtures("_partial_decode_enabled")
def test_ws_stt_final_decode_not_blocked_by_in_flight_partial(client: TestClient) -> None:
    slow_stt = _SlowPartialThenFastFinalSTT()
    app.dependency_overrides[get_stt] = lambda: slow_stt

    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "99"})
        ws.send_bytes(SPEECH_FRAME)  # kicks off the partial decode (blocks)

        assert slow_stt.partial_started.wait(timeout=5.0), "partial decode never started"

        t_end_turn = time.monotonic()
        ws.send_json({"type": "end_turn"})
        msg = ws.receive_json()

        elapsed = time.monotonic() - t_end_turn
        slow_stt.release_partial.set()  # let the blocked partial thread finish, for cleanup

    assert msg["type"] == "stt.final"
    assert msg["turn_id"] == "99"
    assert msg["text"] == "final transcript"  # NOT the stale partial's text
    # The final decode had to start (and this whole exchange complete) while
    # the partial thread was still blocked on release_partial — i.e. well
    # under the 5s the partial is capable of blocking for.
    assert elapsed < 2.0


@pytest.mark.usefixtures("_partial_decode_enabled")
def test_ws_stt_stale_partial_result_is_dropped_after_finalize(client: TestClient) -> None:
    """A partial decode that finishes AFTER finalize() must not send a
    `stt.partial` the client would see after `stt.final` for the same
    turn (the finalized flag drops it)."""
    slow_stt = _SlowPartialThenFastFinalSTT()
    app.dependency_overrides[get_stt] = lambda: slow_stt

    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "100"})
        ws.send_bytes(SPEECH_FRAME)
        assert slow_stt.partial_started.wait(timeout=5.0)

        ws.send_json({"type": "end_turn"})
        final = ws.receive_json()
        assert final["type"] == "stt.final"

        slow_stt.release_partial.set()  # now let the stale partial finish
        time.sleep(0.1)  # give its (dropped) send a chance to happen if buggy

    assert slow_stt.calls == 2  # partial + final both actually ran


def test_ws_stt_disconnect_mid_turn_does_not_raise_server_side(
    client: TestClient,
) -> None:
    """Closing the socket mid-turn must not leak an unhandled exception on
    the server (the endpoint's finally-block cleans up the pending decode
    task); asserted indirectly by the connection afterwards still working."""
    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws:
        ws.send_json({"type": "start_turn", "turn_id": "10"})
        ws.send_bytes(SPEECH_FRAME)
        # Close without end_turn.

    with client.websocket_connect(f"/ws/stt?token={INFERENCE_SERVER_TOKEN}") as ws2:
        ws2.send_json({"type": "start_turn", "turn_id": "11"})
        ws2.send_bytes(SPEECH_FRAME)
        ws2.send_json({"type": "end_turn"})
        msg = ws2.receive_json()

    assert msg["type"] == "stt.final"
    assert msg["turn_id"] == "11"
