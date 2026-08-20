"""MediaRouter — inbound audio decode/feed, barge-in detection, and (future)
outbound flush.

Wraps `audio.pipeline.AudioPipeline` lifecycle for one call: feeding raw
provider audio_frame bytes in, detecting caller speech during TTS playback
(barge-in) via the pipeline's VAD, and — when no STT is configured at all —
a minimal RMS-based fallback barge-in detector so the call still behaves
reasonably in that degraded mode (mirrors the pre-refactor `ws.py` behavior
exactly).

Flush (mid-utterance audio cancellation on the provider side) sends the
internal `flush` event through the adapter (`encode_outbound` decides what,
if anything, that becomes on the wire — e.g. a provider "clear playback"
control message). The identity CloudFone adapter passes it straight
through; a provider with no equivalent can drop it there without `call/`
needing to know.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from audio.codec import ulaw_to_pcm
from audio.pipeline import AudioPipeline
from call.events import FlushPayload
from stt.remote_stt import RemoteSTT
from stt.streaming_remote_stt import StreamingRemoteSTT, StreamingRemoteSTTError
from stt.vad import VADDetector

if TYPE_CHECKING:
    from call.egress import EgressSender

logger = logging.getLogger(__name__)

# (text, emotion, stt_confidence) — confidence feeds the per-turn glassbox
# trace, see obs/turn_trace.py.
OnTranscript = Callable[[str, str | None, float | None], Awaitable[None]]
OnPipelineFailure = Callable[[], Awaitable[None]]
TurnIdProvider = Callable[[], str]

_STREAMING_SAMPLE_RATE = 8000
# Pre-roll (fix for lost first words, e.g. "Dạ" in "Dạ, em muốn đặt lịch..."):
# a `start_turn` only fires once local VAD detects speech, so audio before
# that point was previously just dropped (queue consumer `continue`d past
# it). Keep this many ms of audio buffered ahead of the trigger and flush it
# into the newly-opened turn before the triggering chunk.
_STREAMING_PREROLL_MS = 300
_STREAMING_PREROLL_BYTES = int(_STREAMING_SAMPLE_RATE * 2 * _STREAMING_PREROLL_MS / 1000)


class MediaRouter:
    """Owns at most one `AudioPipeline` (or, when `use_streaming_stt` is on,
    one `StreamingRemoteSTT` session) for the lifetime of a call."""

    def __init__(
        self,
        session_id: str,
        egress: EgressSender | None = None,
        use_silero_vad: bool = False,
    ) -> None:
        self.session_id = session_id
        self.egress = egress
        self.use_silero_vad = use_silero_vad
        self.pipeline: AudioPipeline | None = None
        # Phase 2 streaming STT path — only populated when `start()` is
        # called with a StreamingRemoteSTT instance (feature-flagged off by
        # default, see api/config.py::use_streaming_stt).
        self._streaming_stt: StreamingRemoteSTT | None = None
        self._streaming_vad: VADDetector | None = None
        self._streaming_queue: asyncio.Queue[tuple[bytes, bool] | None] | None = None
        self._turn_id_provider: TurnIdProvider = lambda: "0"

    @property
    def is_speech_active(self) -> bool:
        if self._streaming_vad is not None:
            return self._streaming_vad.speech_active
        return bool(self.pipeline is not None and self.pipeline.is_speech_active)

    def start(
        self,
        stt: object | None,
        on_transcript: OnTranscript,
        on_pipeline_failure: OnPipelineFailure,
        *,
        turn_id_provider: TurnIdProvider | None = None,
    ) -> asyncio.Task | None:
        """Start the background STT task if an STT engine is configured.

        Returns the created task (caller owns cancellation on teardown), or
        None if no STT engine is available (mock/CI mode).
        """
        if stt is None:
            return None

        if isinstance(stt, StreamingRemoteSTT):
            return self._start_streaming(stt, on_transcript, on_pipeline_failure, turn_id_provider)

        self.pipeline = AudioPipeline(stt, use_silero_vad=self.use_silero_vad)

        async def _drain(p: AudioPipeline) -> None:
            # D2 fix, preserved: RemoteSTT raises when the inference tier
            # (MacBook/Tailscale) is unreachable mid-call. Uncaught, that used
            # to silently kill this task, leaving the caller connected but
            # permanently deaf ("silent zombie call"). Catch any pipeline/STT
            # failure and let the caller end the call with a spoken fallback.
            try:
                async for result in p.process():
                    if result.text:
                        await on_transcript(result.text, result.emotion, result.confidence)
                        logger.info(
                            "STT transcript: %r (conf=%.2f, emotion=%s)",
                            result.text, result.confidence, result.emotion,
                        )
            except Exception:
                logger.exception(
                    "pipeline_task: STT/audio pipeline failed session_id=%s "
                    "(inference tier unreachable?) — ending call with fallback",
                    self.session_id,
                )
                await on_pipeline_failure()

        return asyncio.create_task(_drain(self.pipeline))

    def _start_streaming(
        self,
        stt: StreamingRemoteSTT,
        on_transcript: OnTranscript,
        on_pipeline_failure: OnPipelineFailure,
        turn_id_provider: TurnIdProvider | None,
    ) -> asyncio.Task:
        """Phase 2 streaming STT path: one persistent WS connection for the
        whole call, `turn_id` reused from `TurnOrchestrator.turn` (no new
        turn concept introduced — see stt/streaming_remote_stt.py).

        Local VAD (`stt/vad.py`) decides turn boundaries
        (`start_turn`/`end_turn`) and doubles as the barge-in signal, same
        as the AudioPipeline path above.
        """
        self._streaming_stt = stt
        self._streaming_vad = VADDetector(sample_rate=8000, use_silero=self.use_silero_vad)
        self._streaming_queue = asyncio.Queue()
        if turn_id_provider is not None:
            self._turn_id_provider = turn_id_provider

        async def on_final(turn_id: str, text: str, confidence: float) -> None:
            if text:
                await on_transcript(text, None, confidence)
                logger.info(
                    "streaming STT final: %r (turn_id=%s conf=%.2f)", text, turn_id, confidence,
                )

        async def _send_loop(queue: asyncio.Queue[tuple[bytes, bool] | None]) -> None:
            turn_open = False
            preroll: deque[bytes] = deque()
            preroll_bytes = 0
            while True:
                item = await queue.get()
                if item is None:
                    if turn_open:
                        await stt.end_turn()
                    return
                pcm, is_speech = item

                if not turn_open:
                    if not is_speech:
                        # Buffer audio ahead of the eventual VAD trigger so
                        # the turn doesn't start exactly at (and lose audio
                        # before) the trigger point.
                        preroll.append(pcm)
                        preroll_bytes += len(pcm)
                        while preroll_bytes > _STREAMING_PREROLL_BYTES and preroll:
                            preroll_bytes -= len(preroll.popleft())
                        continue
                    turn_open = True
                    await stt.start_turn(self._turn_id_provider())
                    for buffered in preroll:
                        await stt.send_audio(buffered)
                    preroll.clear()
                    preroll_bytes = 0

                await stt.send_audio(pcm)
                if not is_speech and self._streaming_vad is not None and self._streaming_vad.is_end_of_utterance():
                    turn_open = False
                    await stt.end_turn()
                    self._streaming_vad.reset()

        async def _run() -> None:
            send_task: asyncio.Task | None = None
            outcome = "ok"
            try:
                await stt.connect()
                send_task = asyncio.create_task(_send_loop(self._streaming_queue))  # type: ignore[arg-type]
                await stt.listen(on_final=on_final)
            except StreamingRemoteSTTError:
                logger.warning(
                    "streaming STT connection failed session_id=%s — degrading to HTTP "
                    "one-shot RemoteSTT for the remainder of this call instead of hanging "
                    "up (D2: the old HTTP path only ever broke one turn on a failure, "
                    "streaming must not regress that to breaking the whole call)",
                    self.session_id,
                )
                outcome = "degrade"
            except Exception:
                logger.exception(
                    "streaming STT task failed unexpectedly session_id=%s", self.session_id,
                )
                outcome = "fail"
            finally:
                if send_task is not None:
                    send_task.cancel()
                await stt.close()

            if outcome == "degrade":
                self._degrade_to_http_stt(on_transcript, on_pipeline_failure)
            elif outcome == "fail":
                await on_pipeline_failure()

        return asyncio.create_task(_run())

    def _degrade_to_http_stt(
        self, on_transcript: OnTranscript, on_pipeline_failure: OnPipelineFailure
    ) -> None:
        """D2 fix: when the persistent streaming WS fails (connect or
        mid-call disconnect), fall back to the HTTP one-shot `RemoteSTT` for
        the rest of THIS call instead of hanging up. Only a genuinely
        unexpected failure of the fallback pipeline itself still ends the
        call (mirrors the plain HTTP path's own D2 fault-tolerance in
        `start()` above).
        """
        stt = self._streaming_stt
        if stt is None:
            return
        base_url, token = stt.base_url, stt.token
        # Switch feed()/is_speech_active/on_tts_* over to the pipeline branch
        # from here on — this must happen before any further feed() calls.
        self._streaming_stt = None
        self._streaming_vad = None
        self._streaming_queue = None

        self.pipeline = AudioPipeline(RemoteSTT(base_url=base_url, token=token))

        async def _drain(p: AudioPipeline) -> None:
            try:
                async for result in p.process():
                    if result.text:
                        await on_transcript(result.text, result.emotion, result.confidence)
                        logger.info(
                            "STT transcript (HTTP fallback): %r (conf=%.2f, emotion=%s)",
                            result.text, result.confidence, result.emotion,
                        )
            except Exception:
                logger.exception(
                    "pipeline_task: HTTP fallback STT/audio pipeline also failed "
                    "session_id=%s — ending call with fallback",
                    self.session_id,
                )
                await on_pipeline_failure()

        asyncio.create_task(_drain(self.pipeline))

    def feed(self, frame_b64_or_raw: str, *, tts_active: bool) -> bool:
        """Feed one inbound audio_frame's payload to the pipeline.

        Returns True if this frame constitutes a barge-in (caller speaking
        while TTS is active) — the caller decides what to do with that
        (set the interrupt event, bump barge_in_count, log).
        """
        frame_data = base64.b64decode(frame_b64_or_raw)

        if self._streaming_stt is not None and self._streaming_vad is not None:
            pcm = ulaw_to_pcm(frame_data).tobytes()
            is_speech = self._streaming_vad.is_speech(pcm)
            if self._streaming_queue is not None:
                self._streaming_queue.put_nowait((pcm, is_speech))
            # Phase 5.1: speech_active is False during half-duplex suppression
            return tts_active and self._streaming_vad.speech_active

        if self.pipeline is not None:
            self.pipeline.feed(frame_data)
            # Phase 5.1: speech_active is False during half-duplex suppression
            return tts_active and self.pipeline.is_speech_active

        return tts_active and _fallback_rms_speech(frame_data)

    def on_tts_start(self) -> None:
        if self.pipeline is not None:
            self.pipeline._vad.on_tts_start()
        elif self._streaming_vad is not None:
            self._streaming_vad.on_tts_start()

    def on_tts_end(self) -> None:
        if self.pipeline is not None:
            self.pipeline._vad.on_tts_end()
        elif self._streaming_vad is not None:
            self._streaming_vad.on_tts_end()

    async def flush(self, turn: int) -> None:
        """Barge-in: tell the provider to drop any audio already handed to
        it for `turn`. No-op if this MediaRouter wasn't given an egress
        (e.g. tests, or a caller that doesn't care about downstream flush)."""
        if self.egress is not None:
            self.egress.reset_playback()
            await self.egress.send(FlushPayload(turn=turn).to_dict())

    def stop(self) -> None:
        if self.pipeline is not None:
            self.pipeline.stop()
        if self._streaming_queue is not None:
            self._streaming_queue.put_nowait(None)


_FALLBACK_RMS_THRESHOLD = 0.01


def _fallback_rms_speech(frame_data: bytes) -> bool:
    """Crude barge-in detector used only when no STT/pipeline is configured
    at all (mirrors the pre-refactor `ws.py` fallback branch exactly)."""
    import numpy as np  # noqa: PLC0415

    from audio.codec import ulaw_to_pcm  # noqa: PLC0415

    pcm = ulaw_to_pcm(frame_data).astype(np.float32) / 32768.0
    return bool(float(np.sqrt(np.mean(pcm**2))) > _FALLBACK_RMS_THRESHOLD)
