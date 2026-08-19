"""Edge TTS engine — Microsoft Azure TTS via edge-tts package (free, no API key)."""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncGenerator

from tts.params import TTSParams

logger = logging.getLogger(__name__)


class EdgeTTS:
    """Wraps edge-tts for 8kHz PCM telephony output.

    edge-tts produces MP3. We convert to 16-bit 8kHz mono PCM via pydub/ffmpeg.
    Falls back to raw MP3 bytes if conversion fails (should not happen in practice).
    """

    def __init__(self, voice: str = "vi-VN-HoaiMyNeural", rate: str = "+0%") -> None:
        self.voice = voice
        self.rate = rate
        logger.info("EdgeTTS ready (voice=%s)", voice)

    def _effective_rate(self, params: TTSParams | None) -> str:
        if params is not None:
            pct = round((params.speaking_rate - 1.0) * 100)
            sign = "+" if pct >= 0 else ""
            return f"{sign}{pct}%"
        return self.rate

    async def synthesize(self, text: str, params: TTSParams | None = None) -> bytes:
        """Return 16-bit 8kHz mono PCM bytes.

        Runs edge-tts in a separate thread with its own event loop to avoid
        conflicts with the uvicorn event loop (aiohttp incompatibility).
        """
        voice = self.voice
        rate = self._effective_rate(params)
        mp3_bytes = await asyncio.to_thread(_run_edge_tts_sync, text, voice, rate)
        if not mp3_bytes:
            return b""
        return _mp3_to_pcm8k(mp3_bytes)

    async def stream_synthesize(self, text: str, params: TTSParams | None = None) -> AsyncGenerator[bytes, None]:
        """Synthesize full utterance then yield in one chunk (edge-tts is non-streaming)."""
        pcm = await self.synthesize(text, params)

        async def _gen() -> AsyncGenerator[bytes, None]:
            if pcm:
                yield pcm

        return _gen()


def _run_edge_tts_sync(text: str, voice: str, rate: str) -> bytes:
    """Run edge-tts in an isolated event loop (thread-safe, no uvicorn loop conflict)."""
    import edge_tts as _edge_tts  # noqa: PLC0415

    async def _inner() -> bytes:
        communicate = _edge_tts.Communicate(text, voice, rate=rate)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    return asyncio.run(_inner())


def _mp3_to_pcm8k(mp3_bytes: bytes) -> bytes:
    """Convert MP3 bytes → 16-bit 8kHz mono PCM via pydub (ffmpeg required)."""
    try:
        from pydub import AudioSegment  # noqa: PLC0415

        audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)
        return audio.raw_data
    except Exception as exc:
        logger.warning("MP3→PCM conversion failed, returning raw MP3: %s", exc)
        return mp3_bytes
