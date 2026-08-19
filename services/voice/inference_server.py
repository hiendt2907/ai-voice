"""Local inference server — runs on the Macbook, NOT on GCP.

Heavy AI models (Piper TTS, faster-whisper STT) stay on this machine. The voice
worker deployed on GCP k3s calls back here over Tailscale.

Deliberately imports nothing from `api/` so no GCP orchestration config is
pulled in. Configuration is env-only with sane local defaults.

Run:
    cd services/voice
    uv run uvicorn inference_server:app --host 0.0.0.0 --port 8100
"""

from __future__ import annotations

import asyncio
import hmac
import inspect
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from concurrent.futures import Executor, ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from stt.faster_whisper_stt import FasterWhisperSTT
from stt.vad import VADDetector
from tts.params import TTSParams
from tts.piper_tts import PiperTTS

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

OUTPUT_SAMPLE_RATE = 8000
STT_MODEL_SIZE = os.getenv("STT_MODEL_SIZE", "small")
STT_DEVICE = os.getenv("STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "int8")
# Fix for streaming-decode-serialization bug: CT2's default num_workers=1
# means a `stt.final` decode blocks inside the model until any in-flight
# `stt.partial` re-decode finishes, no matter which Python thread/executor
# dispatches it. >=2 lets final and partial actually run concurrently.
STT_NUM_WORKERS = int(os.getenv("STT_NUM_WORKERS", "2"))
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH") or None
WARMUP_ON_STARTUP = os.getenv("INFERENCE_WARMUP", "1") not in ("0", "false", "False")

# D4 remediation: this server is exposed on 0.0.0.0:8100 over the Tailscale
# tailnet with no other access control in front of it. Private transport
# (Tailscale ACLs) is not authentication — every non-health endpoint requires
# a shared service token. Refuse to start rather than run wide open.
INFERENCE_SERVER_TOKEN = os.getenv("INFERENCE_SERVER_TOKEN", "")
if not INFERENCE_SERVER_TOKEN:
    logger.critical(
        "SECURITY: INFERENCE_SERVER_TOKEN is not set. Refusing to start — "
        "this server would otherwise be reachable, unauthenticated, by anyone "
        "on the Tailscale tailnet. Set INFERENCE_SERVER_TOKEN and restart."
    )
    raise RuntimeError(
        "INFERENCE_SERVER_TOKEN environment variable is required and must be non-empty"
    )

# /stt/transcribe accepts a raw PCM16 body; cap it to avoid unbounded memory
# use / DoS from an oversized or malicious upload.
MAX_STT_BODY_BYTES = int(os.getenv("MAX_STT_BODY_BYTES", str(10 * 1024 * 1024)))  # 10MB

# --- /ws/stt streaming STT (Phase 2, D2/D5/D7) -------------------------------
#
# faster-whisper / CTranslate2 has no native incremental-token streaming
# decoder. "Streaming" here means *sliding re-decode*: every
# STREAM_DECODE_INTERVAL_S seconds we re-run transcribe_pcm() on the whole
# audio buffered so far for the current turn and emit whatever it returns as
# `stt.partial`. This is NOT true incremental decoding — later partials
# re-transcribe earlier audio too, which costs CPU relative to a real
# streaming decoder and can make a partial's text non-monotonic (words can
# be revised, not just appended) — but it is what's practically achievable
# on top of faster-whisper today and is architecturally the right shape to
# swap the decode step out later. `stt.final` is always a decode over the
# complete buffered turn audio, so accuracy there does not degrade versus
# the existing one-shot HTTP path.
STREAM_DECODE_INTERVAL_S = float(os.getenv("STREAM_DECODE_INTERVAL_S", "1.0"))
# Round 3 finding: partial (interim, mid-utterance) transcripts were tested
# live and found to be nearly useless (4/5 real samples never even produced
# one before the utterance ended) and occasionally hallucinated content that
# had nothing to do with what was said. Worse, running a partial re-decode
# concurrently with the final decode contends for CPU on non-GPU hosts (two
# near-full-length CT2 decodes racing each other), which made streaming STT
# slower end-to-end than the old HTTP one-shot path. Default this OFF: with
# it off, `_maybe_emit_partial` becomes a no-op and the only decode that ever
# runs per turn is the final one on end-of-utterance/`end_turn`, which is
# both cheaper and matches what real usage showed partials weren't buying
# us. All the partial infrastructure (executor, WS event type, sliding
# re-decode logic) is kept in place, just gated by this flag, so it can be
# re-enabled for experimentation without resurrecting the code.
STREAM_PARTIAL_DECODE_ENABLED = os.getenv("STREAM_PARTIAL_DECODE_ENABLED", "0") not in (
    "0",
    "false",
    "False",
)
STREAM_VAD_SILENCE_MS = int(os.getenv("STREAM_VAD_SILENCE_MS", "400"))
STREAM_VAD_MIN_SPEECH_MS = int(os.getenv("STREAM_VAD_MIN_SPEECH_MS", "200"))
STREAM_SAMPLE_RATE = int(os.getenv("STREAM_SAMPLE_RATE", "8000"))
# NOTE on pre-roll (lost first words, e.g. "Dạ" getting cut): the fix for
# that lives client-side in `call/media.py::MediaRouter._start_streaming` —
# this server only ever sees audio the client already decided to forward
# after `start_turn`, so buffering earlier audio here would be a no-op; the
# client controls when `start_turn` fires relative to VAD.

# Two separate CT2-call dispatch pools (see STT_NUM_WORKERS comment above):
# partial re-decodes are low priority and capped at 1 concurrent decode
# (further partials are simply skipped by `_maybe_emit_partial`'s
# `turn.decoding` guard); final decodes get their own pool so a `stt.final`
# is never queued behind a partial's executor slot even before it reaches
# CT2's internal queue.
_PARTIAL_DECODE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt-partial")
_FINAL_DECODE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="stt-final")


async def verify_service_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Require `Authorization: Bearer <token>` matching INFERENCE_SERVER_TOKEN.

    Applied to every endpoint except /health (fixes D4 — the server previously
    had no authentication at all).
    """
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, INFERENCE_SERVER_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@lru_cache(maxsize=1)
def get_tts() -> PiperTTS:
    """Singleton PiperTTS — model loaded once (avoids 300ms first-call JIT)."""
    return PiperTTS(PIPER_MODEL_PATH) if PIPER_MODEL_PATH else PiperTTS()


@lru_cache(maxsize=1)
def get_stt() -> FasterWhisperSTT:
    """Singleton FasterWhisperSTT — WhisperModel load is expensive."""
    return FasterWhisperSTT(
        model_size=STT_MODEL_SIZE,
        device=STT_DEVICE,
        compute_type=STT_COMPUTE_TYPE,
        num_workers=STT_NUM_WORKERS,
    )


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    speaking_rate: float | None = None
    pitch: float | None = None


class STTResponse(BaseModel):
    text: str
    confidence: float
    is_final: bool
    language: str
    emotion: str | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if WARMUP_ON_STARTUP:
        try:
            await get_tts().warmup()
        except Exception:  # pragma: no cover - warmup is best-effort
            logger.exception("TTS warmup failed")
    yield


app = FastAPI(title="Local Inference Server", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/tts/synthesize", dependencies=[Depends(verify_service_token)])
async def tts_synthesize(
    req: TTSRequest,
    tts: Annotated[PiperTTS, Depends(get_tts)],
) -> Response:
    """Synthesize text → raw PCM16 mono @8kHz in the response body."""
    params = TTSParams(speaking_rate=req.speaking_rate or 1.0)
    pcm = await tts.synthesize(req.text, params)
    return Response(
        content=pcm,
        media_type="audio/L16",
        headers={
            "X-Sample-Rate": str(OUTPUT_SAMPLE_RATE),
            "X-Channels": "1",
            "Content-Length": str(len(pcm)),
        },
    )


@app.post(
    "/stt/transcribe",
    response_model=STTResponse,
    dependencies=[Depends(verify_service_token)],
)
async def stt_transcribe(
    request: Request,
    stt: Annotated[FasterWhisperSTT, Depends(get_stt)],
    sample_rate: Annotated[int, Query(gt=0)] = 8000,
) -> STTResponse:
    """Transcribe raw int16 PCM bytes posted as application/octet-stream."""
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > MAX_STT_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Request body exceeds {MAX_STT_BODY_BYTES} bytes",
        )

    pcm = await request.body()
    if len(pcm) > MAX_STT_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Request body exceeds {MAX_STT_BODY_BYTES} bytes",
        )

    call = stt.transcribe_pcm
    if inspect.iscoroutinefunction(call):
        result = await call(pcm, sample_rate)
    else:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, call, pcm, sample_rate)

    return STTResponse(
        text=result.text,
        confidence=result.confidence,
        is_final=result.is_final,
        language=result.language,
        emotion=result.emotion,
    )


async def _run_stt_decode(
    stt: Any, pcm: bytes, sample_rate: int, executor: Executor | None = None
) -> Any:
    """Run stt.transcribe_pcm off the event loop if it's sync (mirrors
    /stt/transcribe's dispatch above).

    `executor` lets callers pick a dedicated thread pool (see
    _PARTIAL_DECODE_EXECUTOR / _FINAL_DECODE_EXECUTOR) instead of sharing the
    loop's default executor, so a final decode's *dispatch* is never queued
    behind a partial decode's thread slot. Combined with STT_NUM_WORKERS>=2
    (see module docstring), this stops final decodes from being serialized
    behind in-flight partials."""
    call = stt.transcribe_pcm
    if inspect.iscoroutinefunction(call):
        return await call(pcm, sample_rate)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, call, pcm, sample_rate)


class _StreamTurn:
    """Per-`turn_id` streaming STT state, scoped to one WS connection.

    One connection handles one call's worth of turns sequentially (a new
    `start_turn` replaces whatever the previous turn left behind).
    """

    def __init__(self, turn_id: str, sample_rate: int) -> None:
        self.turn_id = turn_id
        self.sample_rate = sample_rate
        self.chunks: list[bytes] = []
        self.vad = VADDetector(
            sample_rate=sample_rate,
            silence_threshold_ms=STREAM_VAD_SILENCE_MS,
            min_speech_duration_ms=STREAM_VAD_MIN_SPEECH_MS,
        )
        self.decoding = False
        self.last_decode_at = 0.0
        self.decode_task: asyncio.Task | None = None
        # Set right before a final decode starts. A partial decode that
        # finishes after this is set must not send a stale `stt.partial`
        # (the client has already gotten/is about to get `stt.final`).
        self.finalized = False

    def abandon_pending_decode(self) -> None:
        """Detach from any in-flight partial decode WITHOUT waiting for it.

        Fix for the final-decode-serialized-behind-partial bug: a partial
        decode's underlying CT2 call runs in a worker thread via
        `run_in_executor`. Once that thread has actually started running,
        cancelling the wrapping asyncio Task (the old `cancel_pending_decode`
        behaviour) does NOT stop the thread — `concurrent.futures.Future
        .cancel()` is a no-op on a future that's already running — so
        `await`-ing the cancelled task would still block until the thread
        finishes. That serialized every `stt.final` behind whatever partial
        re-decode happened to be in flight. This method only requests
        cancellation (best-effort, only helps if the decode hasn't started
        yet) and marks the turn `finalized` so a late partial result is
        dropped, then returns immediately so the final decode can start in
        parallel (see STT_NUM_WORKERS / _FINAL_DECODE_EXECUTOR)."""
        self.finalized = True
        if self.decode_task is not None and not self.decode_task.done():
            self.decode_task.cancel()
        self.decode_task = None


async def _maybe_emit_partial(websocket: WebSocket, stt: Any, turn: _StreamTurn) -> None:
    """Sliding re-decode: re-transcribe everything buffered so far for this
    turn, at most once every STREAM_DECODE_INTERVAL_S. See the module-level
    docstring for why this is re-decode rather than true incremental decode.
    """
    if not STREAM_PARTIAL_DECODE_ENABLED or turn.decoding or not turn.chunks:
        return
    now = time.monotonic()
    if now - turn.last_decode_at < STREAM_DECODE_INTERVAL_S:
        return
    turn.decoding = True
    turn.last_decode_at = now
    pcm = b"".join(turn.chunks)
    turn_id = turn.turn_id

    async def _decode() -> None:
        try:
            result = await _run_stt_decode(
                stt, pcm, turn.sample_rate, executor=_PARTIAL_DECODE_EXECUTOR
            )
            if result.text and not turn.finalized:
                await websocket.send_json(
                    {"type": "stt.partial", "turn_id": turn_id, "text": result.text}
                )
        except asyncio.CancelledError:
            pass  # best-effort cancel from abandon_pending_decode(), never awaited
        except (WebSocketDisconnect, RuntimeError):
            pass  # connection went away mid-decode — nothing to send to
        except Exception:
            logger.exception("streaming STT partial decode failed turn_id=%s", turn_id)
        finally:
            turn.decoding = False

    turn.decode_task = asyncio.create_task(_decode())


async def _finalize_turn(websocket: WebSocket, stt: Any, turn: _StreamTurn) -> None:
    """Decode whatever is buffered for `turn` and emit `stt.final`.

    Invariant: this must never wait for an in-flight partial decode to
    finish — see `_StreamTurn.abandon_pending_decode` and
    `_FINAL_DECODE_EXECUTOR`. The final decode is dispatched to its own
    dedicated executor immediately, in parallel with whatever partial decode
    (if any) is still running.
    """
    turn.abandon_pending_decode()
    pcm = b"".join(turn.chunks)
    turn.chunks = []
    turn.vad.reset()
    if not pcm:
        await websocket.send_json(
            {"type": "stt.final", "turn_id": turn.turn_id, "text": "", "confidence": 0.0}
        )
        return
    try:
        result = await _run_stt_decode(stt, pcm, turn.sample_rate, executor=_FINAL_DECODE_EXECUTOR)
    except Exception:
        logger.exception("streaming STT final decode failed turn_id=%s", turn.turn_id)
        await websocket.send_json(
            {"type": "stt.final", "turn_id": turn.turn_id, "text": "", "confidence": 0.0}
        )
        return
    await websocket.send_json(
        {
            "type": "stt.final",
            "turn_id": turn.turn_id,
            "text": result.text,
            "confidence": result.confidence,
        }
    )


def _authenticated(token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(str(token), INFERENCE_SERVER_TOKEN)


@app.websocket("/ws/stt")
async def ws_stt(
    websocket: WebSocket,
    stt: Annotated[FasterWhisperSTT, Depends(get_stt)],
    token: Annotated[str | None, Query()] = None,
) -> None:
    """Streaming STT gateway (Phase 2, D2/D5/D7).

    Protocol (binary frames = raw PCM16 audio, JSON text frames = control):
      -> {"type": "auth", "token": "..."}          (only needed if no ?token= query param)
      -> {"type": "start_turn", "turn_id": "...", "sample_rate": 8000}
      -> <binary PCM16 chunks...>
      -> {"type": "end_turn"}
      <- {"type": "stt.partial", "turn_id": "...", "text": "..."}          (repeated)
      <- {"type": "stt.endpoint", "turn_id": "..."}                        (VAD silence detected)
      <- {"type": "stt.final", "turn_id": "...", "text": "...", "confidence": 0.0}

    Auth: `?token=` query param (checked at accept time) OR a first
    `{"type":"auth"}` message (checked before anything else is processed).
    Unauthenticated connections are closed with code 4401.

    `/stt/transcribe` (HTTP one-shot) is left completely untouched — this is
    an additive endpoint so the old path remains available as a rollback.
    """
    await websocket.accept()
    authed = _authenticated(token)
    turn: _StreamTurn | None = None

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            text = message.get("text")
            if text is not None:
                try:
                    payload = json.loads(text)
                except (TypeError, ValueError):
                    continue
                mtype = payload.get("type")

                if mtype == "auth":
                    authed = _authenticated(payload.get("token"))
                    if not authed:
                        await websocket.close(code=4401)
                        return
                    continue

                if not authed:
                    await websocket.close(code=4401)
                    return

                if mtype == "start_turn":
                    if turn is not None:
                        turn.abandon_pending_decode()
                    turn_id = str(payload.get("turn_id", ""))
                    sample_rate = int(payload.get("sample_rate") or STREAM_SAMPLE_RATE)
                    turn = _StreamTurn(turn_id=turn_id, sample_rate=sample_rate)
                elif mtype == "end_turn":
                    if turn is not None:
                        await _finalize_turn(websocket, stt, turn)
                        turn = None
                continue

            audio_bytes = message.get("bytes")
            if audio_bytes is None:
                continue
            if not authed:
                await websocket.close(code=4401)
                return
            if turn is None:
                continue  # audio arriving before start_turn — nothing to attach it to

            turn.chunks.append(audio_bytes)
            is_speech = turn.vad.is_speech(audio_bytes)
            await _maybe_emit_partial(websocket, stt, turn)
            if not is_speech and turn.vad.is_end_of_utterance():
                await websocket.send_json({"type": "stt.endpoint", "turn_id": turn.turn_id})
                await _finalize_turn(websocket, stt, turn)
                # Keep turn_id open — the caller may keep talking (e.g. after
                # a brief pause) within the same logical turn until end_turn.
                turn = _StreamTurn(turn_id=turn.turn_id, sample_rate=turn.sample_rate)

    except WebSocketDisconnect:
        pass
    finally:
        if turn is not None:
            turn.abandon_pending_decode()
