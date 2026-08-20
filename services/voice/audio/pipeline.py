"""Audio processing pipeline: raw frames → VAD → STT buffer → transcript events.

Incoming frames are expected as raw int16 PCM bytes at 8kHz (after G.711 decode).
The pipeline accumulates speech frames, detects end-of-utterance, then transcribes.
Supports both sync STT (FasterWhisperSTT) and async STT (ElevenLabsSTT).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncGenerator
from typing import Any

from audio.codec import ulaw_to_pcm
from stt.faster_whisper_stt import STTResult
from stt.vad import VADDetector

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 0.02  # 20ms polling tick


class AudioPipeline:
    """Stateful audio pipeline for a single call session.

    Accepts any STT engine — sync (FasterWhisperSTT) or async (ElevenLabsSTT).

    Usage:
        pipeline = AudioPipeline(stt)
        # In a background task:
        async for result in pipeline.process():
            handle_transcript(result.text)
        # From the event loop:
        pipeline.feed(frame_bytes)   # non-blocking
        if pipeline.is_speech_active:
            ...  # barge-in detection
    """

    def __init__(
        self,
        stt: Any,
        sample_rate: int = 8000,
        is_ulaw: bool = True,
        use_silero_vad: bool = False,
    ) -> None:
        self._stt = stt
        self._sample_rate = sample_rate
        self._is_ulaw = is_ulaw
        self._vad = VADDetector(
            silence_threshold_ms=400, sample_rate=sample_rate, use_silero=use_silero_vad
        )
        self._pcm_buffer: list[bytes] = []
        self._frame_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._stt_is_async = inspect.iscoroutinefunction(getattr(stt, "transcribe_pcm", None))

    @property
    def is_speech_active(self) -> bool:
        """True when the VAD has recently detected speech energy — use for barge-in detection."""
        return self._vad.speech_active

    def feed(self, frame_bytes: bytes) -> None:
        """Feed a raw audio frame into the pipeline (non-blocking)."""
        self._frame_queue.put_nowait(frame_bytes)

    def stop(self) -> None:
        """Signal pipeline to drain and stop."""
        self._frame_queue.put_nowait(None)

    async def process(self) -> AsyncGenerator[STTResult, None]:
        """Async generator: yields STTResult whenever end-of-utterance is detected."""
        while True:
            try:
                frame = await asyncio.wait_for(self._frame_queue.get(), timeout=_POLL_INTERVAL_S)
            except TimeoutError:
                # Check for end-of-utterance during silence periods
                if self._vad.is_end_of_utterance() and self._pcm_buffer:
                    result = await self._flush_buffer()
                    if result.text:
                        yield result
                continue

            if frame is None:
                # Drain remaining buffer on stop
                if self._pcm_buffer:
                    result = await self._flush_buffer()
                    if result.text:
                        yield result
                break

            pcm = ulaw_to_pcm(frame).tobytes() if self._is_ulaw else frame

            is_speech = self._vad.is_speech(pcm)
            if is_speech:
                self._pcm_buffer.append(pcm)
            elif self._vad.is_end_of_utterance() and self._pcm_buffer:
                result = await self._flush_buffer()
                if result.text:
                    yield result

    async def _flush_buffer(self) -> STTResult:
        pcm_bytes = b"".join(self._pcm_buffer)
        self._pcm_buffer.clear()
        self._vad.reset()
        logger.debug("STT flush: %d bytes of PCM", len(pcm_bytes))
        if self._stt_is_async:
            return await self._stt.transcribe_pcm(pcm_bytes, self._sample_rate)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._stt.transcribe_pcm, pcm_bytes, self._sample_rate
        )
