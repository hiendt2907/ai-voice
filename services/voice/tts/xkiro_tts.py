"""xKiro TTS engine — cloud Vietnamese TTS via api.xkiro.com.

xKiro returns MP3; we decode to 16-bit 8kHz mono PCM (same pydub/ffmpeg path
as EdgeTTS) so the rest of the pipeline (egress.send_audio's audio-position
playback clock, barge-in flush) sees the same wire format regardless of
engine. Interface matches ElevenLabsTTS/RemoteTTS (synthesize /
stream_synthesize / stream_step) so it drops into TTSChain unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
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

_TARGET_SR = 8000
# 20ms @ 8kHz mono int16 — one telephony frame, so the first decoded audio
# reaches the caller as soon as a single frame exists rather than after a
# larger read buffer fills.
_PCM_CHUNK_BYTES = 320

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
        """True streaming: yield 20ms PCM frames as xKiro's MP3 arrives.

        MP3 can't be decoded frame-by-frame with a one-shot decoder like
        pydub, which is why this previously buffered the whole response and
        yielded it as a single chunk — making time-to-first-audio equal to
        *total* synthesis time (~0.9-1.5s measured) instead of time to first
        byte. A persistent ffmpeg subprocess decodes incrementally, so the
        first frames reach the caller while xKiro is still generating.
        """
        if not text or not text.strip():

            async def _empty() -> AsyncGenerator[bytes, None]:
                return
                yield b""  # pragma: no cover

            return _empty()

        return self._stream_pcm(text)

    async def _stream_pcm(self, text: str) -> AsyncGenerator[bytes, None]:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            # Without these, ffmpeg buffers a chunk of input to probe the
            # format before emitting anything — pure added latency when we
            # already know xKiro returns MP3.
            "-f", "mp3", "-probesize", "32", "-analyzeduration", "0",
            "-i", "pipe:0",
            "-ar", str(_TARGET_SR), "-ac", "1", "-f", "s16le",
            "-flush_packets", "1",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdin is not None and proc.stdout is not None

        async def _feed() -> None:
            """Pump xKiro's MP3 bytes into the decoder as they arrive."""
            try:
                async with self._get_client().stream(
                    "POST", self._tts_url, headers=self._headers(), json=self._payload(text)
                ) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes():
                        proc.stdin.write(chunk)
                        await proc.stdin.drain()
            except (httpx.HTTPError, BrokenPipeError, ConnectionResetError) as exc:
                logger.warning("xKiro TTS stream error: %s", exc)
            finally:
                with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                    proc.stdin.close()

        feeder = asyncio.create_task(_feed())
        try:
            while True:
                pcm = await proc.stdout.read(_PCM_CHUNK_BYTES)
                if not pcm:
                    break
                yield pcm
        finally:
            feeder.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await feeder
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()

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
