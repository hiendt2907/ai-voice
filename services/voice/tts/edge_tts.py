"""Edge TTS engine — Microsoft Azure TTS via edge-tts package (free, no API key)."""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Any

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

    async def synthesize(self, text: str) -> bytes:
        """Return 16-bit 8kHz mono PCM bytes.

        Runs edge-tts in a separate thread with its own event loop to avoid
        conflicts with the uvicorn event loop (aiohttp incompatibility).
        """
        voice, rate = self.voice, self.rate
        mp3_bytes = await asyncio.to_thread(_run_edge_tts_sync, text, voice, rate)
        if not mp3_bytes:
            return b""
        return _mp3_to_pcm8k(mp3_bytes)


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
