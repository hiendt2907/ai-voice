"""ElevenLabs TTS backend — drop-in replacement for GwenTTS.

Outputs PCM 8kHz int16 directly (no resampling needed).
TTFA ~500-600ms for short utterances.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator

from metrics.elevenlabs import record_request as _record_el
from tts.params import TTSParams

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "eleven_v3"
_DEFAULT_LANG = "vi"
_PCM_FORMAT = "pcm_8000"
_CHUNK_SIZE = 1024  # bytes per streaming chunk

_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")

# Map prosody pause tiers → punctuation for combined-text synthesis
_PAUSE_PUNCT: dict[str, str] = {
    "none": " ",
    "micro": ", ",
    "short": ", ",
    "breath": "... ",
    "medium": ". ",
    "long": ". ",
    "turn": ". ",
}


class ElevenLabsTTS:
    """Vietnamese TTS via ElevenLabs API.

    Compatible interface with GwenTTS: same synthesize() / stream_synthesize() signatures.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = _DEFAULT_MODEL,
        language_code: str = _DEFAULT_LANG,
        redis: object | None = None,
        stability: float = 0.71,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True,
        speed: float = 1.0,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._model_id = model_id
        self._language_code = language_code
        self._client: object | None = None
        self._redis = redis
        self._stability = stability
        self._similarity_boost = similarity_boost
        self._style = style
        self._use_speaker_boost = use_speaker_boost
        self._speed = speed

    def _get_client(self) -> object:
        if self._client is None:
            try:
                from elevenlabs.client import ElevenLabs  # type: ignore[import]
            except ImportError as exc:
                raise RuntimeError(
                    "elevenlabs not installed. Run: uv add elevenlabs"
                ) from exc
            self._client = ElevenLabs(api_key=self._api_key)
            logger.info("ElevenLabs TTS client initialised (voice=%s)", self._voice_id)
        return self._client

    def _voice_settings(self, params: TTSParams | None = None) -> object:
        from elevenlabs import VoiceSettings  # type: ignore[import]
        if params is not None:
            return VoiceSettings(
                stability=params.stability,
                similarity_boost=params.similarity_boost,
                style=params.style,
                use_speaker_boost=self._use_speaker_boost,
                speed=params.speaking_rate,
            )
        return VoiceSettings(
            stability=self._stability,
            similarity_boost=self._similarity_boost,
            style=self._style,
            use_speaker_boost=self._use_speaker_boost,
            speed=self._speed,
        )

    def _stream_sync(self, text: str, params: TTSParams | None = None) -> bytes:
        """Synchronous streaming → concatenated PCM 8kHz bytes."""
        client = self._get_client()
        chunks = client.text_to_speech.stream(  # type: ignore[union-attr]
            text=text,
            voice_id=self._voice_id,
            model_id=self._model_id,
            language_code=self._language_code,
            output_format=_PCM_FORMAT,
            voice_settings=self._voice_settings(params),
        )
        return b"".join(chunks)

    async def synthesize(self, text: str, params: TTSParams | None = None) -> bytes:
        """Async synthesis → raw int16 PCM bytes at 8kHz."""
        loop = asyncio.get_event_loop()
        t0 = time.monotonic()
        try:
            result = await loop.run_in_executor(None, self._stream_sync, text, params)
            latency_ms = (time.monotonic() - t0) * 1000
            await _record_el(self._redis, latency_ms=latency_ms, ok=True)
            return result
        except Exception:
            await _record_el(self._redis, latency_ms=None, ok=False)
            raise

    async def stream_synthesize(
        self, text: str, params: TTSParams | None = None, chunk_size: int = _CHUNK_SIZE
    ) -> AsyncGenerator[bytes, None]:
        """Async streaming synthesis → yield PCM chunks as they arrive."""
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        redis = self._redis

        def _producer() -> None:
            t0 = time.monotonic()
            ok = False
            try:
                client = self._get_client()
                stream = client.text_to_speech.stream(  # type: ignore[union-attr]
                    text=text,
                    voice_id=self._voice_id,
                    model_id=self._model_id,
                    language_code=self._language_code,
                    output_format=_PCM_FORMAT,
                    voice_settings=self._voice_settings(params),
                )
                for chunk in stream:
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
                ok = True
            except Exception as exc:
                logger.error("ElevenLabs stream error: %s", exc)
            finally:
                latency_ms = (time.monotonic() - t0) * 1000 if ok else None
                asyncio.run_coroutine_threadsafe(
                    _record_el(redis, latency_ms=latency_ms, ok=ok), loop
                )
                loop.call_soon_threadsafe(queue.put_nowait, None)

        thread = asyncio.get_event_loop().run_in_executor(None, _producer)

        async def _gen() -> AsyncGenerator[bytes, None]:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
            await thread

        return _gen()

    async def stream_step(
        self,
        beats: list[dict],
        slots: dict[str, str] | None = None,
        interrupt: asyncio.Event | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """Stream an entire script step as a single ElevenLabs HTTP call.

        Combines all beats into one text string using punctuation-based pauses,
        making one streaming request instead of N per beat. Yields PCM 8kHz chunks.
        """
        slots = slots or {}
        parts: list[str] = []
        for beat in beats:
            raw_text: str = beat.get("text", "")
            text = _TEMPLATE_VAR.sub(lambda m: slots.get(m.group(1), m.group(0)), raw_text)
            if not text.strip():
                continue
            pause_tier: str = beat.get("pause_after", "none")
            speaking_rate: float = beat.get("speaking_rate", 1.0)
            # Wrap in SSML prosody tag when rate deviates meaningfully from normal
            if speaking_rate <= 0.85:
                text = f'<prosody rate="slow">{text}</prosody>'
            elif speaking_rate >= 1.15:
                text = f'<prosody rate="fast">{text}</prosody>'
            if beat.get("emphasis"):
                text = f"<emphasis>{text}</emphasis>"
            parts.append(text + _PAUSE_PUNCT.get(pause_tier, " "))

        combined = "".join(parts).rstrip()

        async def _empty() -> AsyncGenerator[bytes, None]:
            return
            yield b""  # pragma: no cover

        if not combined:
            return _empty()

        gen = await self.stream_synthesize(combined)

        async def _guarded() -> AsyncGenerator[bytes, None]:
            async for chunk in gen:
                if interrupt and interrupt.is_set():
                    return
                yield chunk

        return _guarded()
