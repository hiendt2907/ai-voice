"""xKiro TTS engine — cloud Vietnamese TTS via api.xkiro.com.

xKiro returns MP3; we decode to 16-bit 8kHz mono PCM (same pydub/ffmpeg path
as EdgeTTS) so the rest of the pipeline (egress.send_audio's audio-position
playback clock, barge-in flush) sees the same wire format regardless of
engine. Interface matches ElevenLabsTTS/RemoteTTS (synthesize /
stream_synthesize / stream_step) so it drops into TTSChain unchanged.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from collections.abc import AsyncGenerator

import httpx

from tts.params import TTSParams

logger = logging.getLogger(__name__)

_DEFAULT_URL = "https://api.xkiro.com/v1/audio/speech"
_DEFAULT_MODEL = "xkiro-voice"
_DEFAULT_TIMEOUT = 30.0

_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")

_PAUSE_PUNCT: dict[str, str] = {
    "none": " ",
    "micro": ", ",
    "short": ", ",
    "breath": "... ",
    "medium": ". ",
    "long": ". ",
    "turn": ". ",
}


class XkiroTTSError(RuntimeError):
    """Raised on HTTP/connection failure so TTSChain's circuit breaker can
    record the failure and fall back to the next engine."""


class XkiroTTS:
    """Vietnamese TTS via xKiro's OpenAI-compatible `/audio/speech` endpoint."""

    def __init__(
        self,
        api_key: str,
        voice: str,
        tts_url: str = _DEFAULT_URL,
        model: str = _DEFAULT_MODEL,
        timeout_s: float = _DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._voice = voice
        self._tts_url = tts_url
        self._model = model
        self._timeout_s = timeout_s
        self._client = client
        self._client_owned = client is None
        logger.info("XkiroTTS ready (url=%s, voice=%s)", tts_url, voice)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._client_owned:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, text: str) -> dict[str, object]:
        return {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "mp3",
            "stream": True,
        }

    async def synthesize(self, text: str, params: TTSParams | None = None) -> bytes:
        """POST text → raw int16 PCM bytes at 8kHz (decoded from xKiro's MP3)."""
        if not text or not text.strip():
            return b""
        try:
            resp = await self._get_client().post(
                self._tts_url, headers=self._headers(), json=self._payload(text)
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise XkiroTTSError(
                f"xKiro TTS {self._tts_url} returned HTTP {exc.response.status_code}: "
                f"{exc.response.text[:500]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise XkiroTTSError(f"xKiro TTS {self._tts_url} unreachable: {exc}") from exc
        return _mp3_to_pcm8k(resp.content)

    async def stream_synthesize(
        self, text: str, params: TTSParams | None = None
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize full utterance then yield in one chunk.

        xKiro streams MP3 frames over HTTP, but MP3 cannot be decoded frame-
        by-frame into raw PCM without a persistent decoder (see the ffmpeg
        subprocess trick in the local benchmark scripts) — same simplification
        EdgeTTS already makes for its own MP3 output.
        """
        pcm = await self.synthesize(text, params)

        async def _gen() -> AsyncGenerator[bytes, None]:
            if pcm:
                yield pcm

        return _gen()

    async def stream_step(
        self,
        beats: list[dict],
        slots: dict[str, str] | None = None,
        interrupt: asyncio.Event | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """Stream a whole script step as one xKiro call (beats joined by pauses)."""
        slots = slots or {}
        parts: list[str] = []
        for beat in beats:
            raw_text: str = beat.get("text", "")
            text = _TEMPLATE_VAR.sub(lambda m: slots.get(m.group(1), m.group(0)), raw_text)
            if not text.strip():
                continue
            pause_tier: str = beat.get("pause_after", "none")
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
                if interrupt is not None and interrupt.is_set():
                    return
                yield chunk

        return _guarded()


def _mp3_to_pcm8k(mp3_bytes: bytes) -> bytes:
    """Convert MP3 bytes → 16-bit 8kHz mono PCM via pydub (ffmpeg required)."""
    try:
        from pydub import AudioSegment  # noqa: PLC0415

        audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)
        return audio.raw_data
    except Exception as exc:
        logger.warning("xKiro MP3→PCM conversion failed, returning raw MP3: %s", exc)
        return mp3_bytes
