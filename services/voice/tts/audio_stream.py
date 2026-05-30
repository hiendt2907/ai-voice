"""Beat sequence → audio byte stream.

Converts the script's prosody beat format into actual audio bytes,
inserting silent PCM frames for pause_ms gaps between beats.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Protocol

import numpy as np

from tts.prosody import PAUSE_DURATION_MS

_SAMPLE_RATE = 8000  # telephony 8kHz


class TTSEngine(Protocol):
    """Structural protocol satisfied by both ElevenLabsTTS and GwenTTS."""

    async def synthesize(self, text: str) -> bytes: ...

    async def stream_synthesize(self, text: str) -> AsyncGenerator[bytes, None]: ...


def _silence_pcm(duration_ms: int) -> bytes:
    """Generate silence as int16 PCM bytes."""
    n_samples = int(_SAMPLE_RATE * duration_ms / 1000)
    return np.zeros(n_samples, dtype=np.int16).tobytes()


class BeatsAudioStream:
    """Stream beats as audio bytes, including pauses between beats.

    Args:
        tts: Synthesizer instance shared across the session.
        interrupt_event: Set by VAD barge-in detection to cancel TTS.
    """

    def __init__(
        self,
        tts: TTSEngine,
        interrupt_event: asyncio.Event | None = None,
    ) -> None:
        self._tts = tts
        self._interrupt = interrupt_event

    async def stream(
        self,
        beats: list[dict],
        slots: dict[str, str] | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """Yield audio chunks for each beat, then silence for pause_after."""
        import re  # noqa: PLC0415

        _TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")
        slots = slots or {}

        for beat in beats:
            if self._interrupt and self._interrupt.is_set():
                return

            raw_text: str = beat.get("text", "")
            text = _TEMPLATE_VAR.sub(lambda m: slots.get(m.group(1), m.group(0)), raw_text)

            if not text.strip():
                continue

            # Synthesize this beat
            async for chunk in await self._tts.stream_synthesize(text):
                if self._interrupt and self._interrupt.is_set():
                    return
                yield chunk

            # Pause after beat
            pause_tier: str = beat.get("pause_after", "none")
            pause_ms = PAUSE_DURATION_MS.get(pause_tier, 0)
            if pause_ms > 0:
                yield _silence_pcm(pause_ms)
