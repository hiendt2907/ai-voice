"""Regression tests for the D1/D2 stop-the-bleeding patches in api/routers/ws.py.

D1 (turn_handler had no exception guard): any exception raised while
processing a turn (RAG error, TTS chain exhaustion, Redis blip, ...) used to
kill the background task permanently. The WebSocket stayed open, audio kept
arriving, and the caller was met with silence forever.

D2 (STT/inference-tier failures killed the pipeline task silently):
RemoteSTT raises RemoteSTTError when the MacBook/Tailscale inference tier is
unreachable mid-call. Nothing caught it, so it propagated out of
AudioPipeline.process() and killed pipeline_task with nobody retrieving the
exception — a "silent zombie call".

Both are now caught at their task boundary (turn_handler / _drain_pipeline),
logged with session context, and followed by a spoken Vietnamese fallback
line + a clean hangup — never a silent hang.

D3 (HANGUP raced turn_handler's in-flight terminal-step status update):
turn_handler() runs decoupled from the WS receive loop via transcript_queue
(so barge-in can interrupt mid-turn), so a HANGUP arriving while the last
utterance is still being processed — e.g. still streaming the farewell TTS,
about to set state.status="completed" on landing on a terminal step — used
to reach `_post_call_events` before that update happened, persisting a
normally-finished call as status="error". Found via a real-conversation test
(booking flow ending in "goodbye" → farewell) where the transcript was a
complete, correct booking but the DB row said "error". Fixed by awaiting the
turn_handler task (bounded) before reading state in the `finally` block.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import queue
import threading
import time

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.remote_config as remote_config_module
import api.routers.ws as ws_module
import call.turn as turn_module
from api.remote_config import (
    AiConfig,
    ConversationConfig,
    NotifyConfig,
    SttConfig,
    SystemConfig,
    TtsConfig,
    VoiceWorkerConfig,
)
from audio.codec import pcm_to_ulaw
from cloudfone.protocol import OutboundEvent

MINIMAL_SCRIPT = {
    "id": "test-script",
    "entry_step": "greeting",
    "steps": [
        {
            "id": "greeting",
            "type": "speak_listen",
            "variants": [{"id": "v1", "beats": [{"text": "Xin chào", "pause_after": "turn"}]}],
            "reprompt_variants": [{"id": "r1", "beats": [{"text": "R1", "pause_after": "turn"}]}],
            "transitions": [],
            "fallback_goto": "greeting",
            "max_no_match": 5,
        },
    ],
    "intents": [],
}


def _fake_system_config() -> SystemConfig:
    """Minimal SystemConfig — no real synthesis/LLM/conversation engine, so
    the test never depends on Redis, NestJS, or model downloads."""
    return SystemConfig(
        ai=AiConfig(
            ollama_base_url="http://localhost:11434/v1",
            ollama_model="qwen2.5:latest",
            nlu_timeout_ms=800,
            response_timeout_ms=2000,
            fallback_to_substring=True,
        ),
        stt=SttConfig(),
        tts=TtsConfig(
            engine="none",
            voice="",
            sample_rate=8000,
            speed_factor=1.0,
            elevenlabs_api_key="",
            elevenlabs_voice_id="",
            elevenlabs_model_id="",
        ),
        notify=NotifyConfig(
            platform="telegram",
            teams_webhook_url="",
            telegram_bot_token="",
            telegram_group_id="",
            question_timeout_seconds=60,
            callback_delay_minutes=5,
        ),
        voice_worker=VoiceWorkerConfig(
            internal_url="http://localhost:8000",
            max_concurrent_sessions=10,
            session_cache_ttl_seconds=300,
        ),
        conversation=ConversationConfig(enabled=False),
    )


@pytest.fixture(autouse=True)
def _patch_remote_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid any real Redis / NestJS calls — RemoteConfig.load() is patched
    to return a static, minimal config."""

    async def _fake_load(self: object) -> SystemConfig:
        return _fake_system_config()

    monkeypatch.setattr(remote_config_module.RemoteConfig, "load", _fake_load)


@pytest.fixture(autouse=True)
def _isolate_ws_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """ws.py's `_settings` is a module-level Settings() built from the real
    services/voice/.env at import time. Force the flags that would otherwise
    make these tests depend on real TTS engines (edge-tts network calls,
    local Piper models) or a real Ollama LLM for NLU — this suite only cares
    about the D1/D2 fault-tolerance behaviour, not real synthesis/NLU."""
    monkeypatch.setattr(ws_module._settings, "use_real_tts", False)
    monkeypatch.setattr(ws_module._settings, "use_llm_nlu", False)


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(ws_module.router)
    return test_app


def _speech_frame_ulaw(amplitude: int = 8000, n_samples: int = 160) -> str:
    """One 20ms frame of loud PCM, μ-law encoded + base64'd (wire format)."""
    pcm = (np.ones(n_samples, dtype=np.int16) * amplitude)
    ulaw = pcm_to_ulaw(pcm)
    return base64.b64encode(ulaw).decode()


def _receive_json_with_timeout(websocket: object, timeout: float = 5.0) -> dict:
    """websocket.receive_json() blocks forever if the server never sends
    another message. Bound it so a regression (a real silent hang) fails the
    test with a clear TimeoutError instead of freezing the test run."""
    result: "queue.Queue[tuple[str, object]]" = queue.Queue(maxsize=1)

    def _recv() -> None:
        try:
            result.put(("ok", websocket.receive_json()))  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - defensive
            result.put(("err", exc))

    thread = threading.Thread(target=_recv, daemon=True)
    thread.start()
    try:
        kind, payload = result.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError(f"no WS message received within {timeout}s") from exc
    if kind == "err":
        raise payload  # type: ignore[misc]
    return payload  # type: ignore[return-value]


def test_turn_handler_exception_ends_call_with_fallback_instead_of_hanging(
    caplog: pytest.LogCaptureFixture, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D1: an unhandled exception inside process_utterance must not kill
    turn_handler silently — it must be logged with session context and the
    call must end with a spoken fallback + hangup."""

    async def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated RAG/TTS/Redis failure mid-turn")

    # D1's guard now lives in call.turn.TurnOrchestrator.turn_handler (moved
    # out of api/routers/ws.py in the Phase 1 call-core extraction) — patch
    # the FSM entry point where it's actually called from.
    monkeypatch.setattr(turn_module, "async_process_turn", _boom)

    with caplog.at_level(logging.ERROR, logger="call.turn"), TestClient(app) as client:
        with client.websocket_connect("/ws/call?provider=cloudfone") as websocket:
            websocket.send_json({
                "event": "start",
                "session_id": "test-session-d1",
                "script": MINIMAL_SCRIPT,
            })

            # Drain the greeting beat sent on START.
            events: list[dict] = [_receive_json_with_timeout(websocket)]

            # Trigger a turn — async_process_turn (mocked) raises.
            websocket.send_json({"event": "utterance", "text": "đặt lịch khám"})

            # Collect events until hangup or a safety cap is hit.
            seen_hangup = False
            for _ in range(20):
                msg = _receive_json_with_timeout(websocket)
                events.append(msg)
                if msg.get("event") == OutboundEvent.HANGUP:
                    seen_hangup = True
                    break

    assert seen_hangup, f"expected a hangup event after the turn exception, got: {events}"

    # The exception must have been logged with session context — proof the
    # task didn't die silently (no "Task exception was never retrieved").
    assert any(
        "unhandled exception processing utterance" in rec.message
        and "test-session-d1" in rec.message
        for rec in caplog.records
    ), "expected turn_handler to log the exception with session_id context"


def test_stt_failure_ends_call_with_fallback_instead_of_silent_zombie(
    caplog: pytest.LogCaptureFixture, app: FastAPI
) -> None:
    """D2: when the remote inference tier (MacBook offline / Tailscale down)
    fails mid-call, RemoteSTT raises. That must not kill pipeline_task
    silently — it must be caught, logged, and followed by a spoken fallback
    + clean hangup."""

    class _FailingSTT:
        async def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 8000):  # noqa: ANN201
            raise RuntimeError("simulated RemoteSTTError: inference tier unreachable")

    app.state.stt = _FailingSTT()

    # D2's guard now lives in call.media.MediaRouter (moved out of
    # api/routers/ws.py in the Phase 1 call-core extraction).
    with caplog.at_level(logging.ERROR, logger="call.media"), TestClient(app) as client:
        with client.websocket_connect("/ws/call?provider=cloudfone") as websocket:
            websocket.send_json({
                "event": "start",
                "session_id": "test-session-d2",
                "script": MINIMAL_SCRIPT,
            })

            events: list[dict] = [_receive_json_with_timeout(websocket)]

            # Feed >= min_speech_duration_ms (200ms) of "speech" energy,
            # paced in real time so the VAD's accumulated-speech-duration
            # check (based on wall-clock timestamps, not frame count) is
            # satisfied, then go silent so it naturally declares
            # end-of-utterance and flushes the buffer through the (failing)
            # STT. Sending all frames back-to-back with no delay would make
            # first-speech-ts ≈ last-speech-ts and never clear that check.
            frame = _speech_frame_ulaw()
            for _ in range(15):  # 15 * ~25ms = ~375ms of paced "speech"
                websocket.send_json({"event": "audio_frame", "data": frame})
                time.sleep(0.025)

            seen_hangup = False
            for _ in range(60):
                msg = _receive_json_with_timeout(websocket, timeout=10.0)
                events.append(msg)
                if msg.get("event") == OutboundEvent.HANGUP:
                    seen_hangup = True
                    break

    assert seen_hangup, f"expected a hangup event after the STT failure, got: {events}"

    assert any(
        "pipeline_task: STT/audio pipeline failed" in rec.message
        and "test-session-d2" in rec.message
        for rec in caplog.records
    ), "expected _drain_pipeline to log the STT failure with session_id context"


TERMINAL_SCRIPT = {
    "id": "test-script",
    "entry_step": "greeting",
    "steps": [
        {
            "id": "greeting",
            "type": "speak_listen",
            "variants": [{"id": "v1", "beats": [{"text": "Xin chào", "pause_after": "turn"}]}],
            "reprompt_variants": [{"id": "r1", "beats": [{"text": "R1", "pause_after": "turn"}]}],
            "transitions": [{"when": "intent == 'confirm'", "goto": "farewell"}],
            "fallback_goto": "farewell",
            "max_no_match": 2,
        },
        {
            "id": "farewell",
            "type": "speak",
            "variants": [{"id": "v1", "beats": [{"text": "Tạm biệt.", "pause_after": "long"}]}],
        },
    ],
    "intents": [{"intent": "confirm", "examples": [{"text": "đúng rồi"}]}],
}


def test_hangup_racing_inflight_turn_does_not_lose_completed_status(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D3: HANGUP arriving while the last utterance is still mid-processing
    must not make _post_call_events read a stale (pre-transition) state.

    "đúng rồi" is matched via the deterministic affirm-heuristic guided path
    in nlu.intent_resolver (no embedding model needed, so this stays fast and
    independent of the real NLU store), landing on the terminal "farewell"
    step. async_process_turn is wrapped with an artificial delay so the
    turn is still in flight when HANGUP is sent right behind it — reproducing
    the race without relying on real-world timing.
    """
    real_async_process_turn = turn_module.async_process_turn

    async def _delayed(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(0.3)
        return await real_async_process_turn(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(turn_module, "async_process_turn", _delayed)

    posted_status: dict[str, str | None] = {}
    real_post_call_events = ws_module._post_call_events

    async def _capture_then_post(ctx: object, turn_orch: object, started_at: float) -> None:
        posted_status["status"] = (
            turn_orch.state.status if turn_orch.state is not None else None  # type: ignore[attr-defined]
        )
        await real_post_call_events(ctx, turn_orch, started_at)  # type: ignore[arg-type]

    monkeypatch.setattr(ws_module, "_post_call_events", _capture_then_post)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/call?provider=cloudfone") as websocket:
            websocket.send_json({
                "event": "start",
                "session_id": "test-session-d3",
                "script": TERMINAL_SCRIPT,
            })
            _receive_json_with_timeout(websocket)  # drain the greeting beat

            websocket.send_json({"event": "utterance", "text": "đúng rồi"})
            # Sent immediately behind the utterance, before the artificially
            # delayed turn has any chance to finish — this is the race.
            websocket.send_json({"event": "hangup"})

            events: list[dict] = []
            for _ in range(20):
                msg = _receive_json_with_timeout(websocket, timeout=5.0)
                events.append(msg)
                if msg.get("event") == OutboundEvent.HANGUP:
                    break

    assert posted_status.get("status") == "completed", (
        f"expected the in-flight turn to finish landing on the terminal step "
        f"before call-events were posted, got status={posted_status.get('status')!r} "
        f"events={events}"
    )
