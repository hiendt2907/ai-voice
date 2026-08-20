"""Remote TTS engine — delegates synthesis to an inference server over HTTP.

The heavy local models (Piper / qwen-tts / faster-whisper) run on a separate
machine exposing `POST /tts/synthesize`. This adapter keeps the voice worker
image small: only httpx is required.

Interface is compatible with `TTSChain` (synthesize / stream_synthesize) and
with `api/routers/ws.py` (stream_step).
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncGenerator

import httpx

from tts.params import TTSParams

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_CHUNK_SIZE = 1024  # bytes per streaming chunk (8kHz int16 → 64ms)

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


class RemoteTTSError(RuntimeError):
    """Raised when the remote inference server is unreachable or returns an error.

    Surfaced (not swallowed) so `TTSChain`'s circuit breaker records the failure
    and falls back to the next engine.
    """


class RemoteTTS:
    """TTS via a remote inference server returning raw PCM16 8kHz mono."""

    def __init__(
        self,
        base_url: str,
        timeout_s: float = _DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
        token: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client = client
        self._client_owned = client is None
        self._token = token
        if not token:
            logger.warning(
                "RemoteTTS configured without inference_server_token — requests to "
                "%s will be rejected with 401 once server-side auth is enabled",
                self._base_url,
            )
        logger.info("RemoteTTS ready (base_url=%s)", self._base_url)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def aclose(self) -> None:
        if self._client is not None and self._client_owned:
            await self._client.aclose()
            self._client = None

    async def synthesize(self, text: str, params: TTSParams | None = None) -> bytes:
        """POST text → raw int16 PCM bytes at 8kHz.

        Raises RemoteTTSError on timeout / connection failure / non-2xx response.
        """
        if not text or not text.strip():
            return b""

        payload: dict[str, object] = {
            "text": text,
            "speaking_rate": params.speaking_rate if params is not None else None,
            "pitch": None,
        }
        url = f"{self._base_url}/tts/synthesize"
        try:
            resp = await self._get_client().post(
                url, json=payload, timeout=self._timeout_s, headers=self._auth_headers()
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RemoteTTSError(
                f"Remote TTS {url} returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RemoteTTSError(f"Remote TTS {url} unreachable: {exc}") from exc
        return resp.content

    async def stream_synthesize(
        self, text: str, params: TTSParams | None = None, chunk_size: int = _CHUNK_SIZE
    ) -> AsyncGenerator[bytes, None]:
        """Stream from the inference server's `/tts/synthesize/stream`
        endpoint — each HTTP response chunk is one of Piper's own
        per-sentence audio chunks (see `PiperTTS.stream_synthesize`), sent
        as soon as that sentence is synthesized. Previously this buffered
        the whole utterance via the one-shot endpoint before yielding
        anything (TTFA ≈ full synthesis time — see
        docs/ai-streaming-voice-architecture-proposal.md §197/§1074/§1182).
        """
        if not text or not text.strip():
            async def _empty() -> AsyncGenerator[bytes, None]:
                return
                yield b""  # pragma: no cover

            return _empty()

        payload: dict[str, object] = {
            "text": text,
            "speaking_rate": params.speaking_rate if params is not None else None,
            "pitch": None,
        }
        url = f"{self._base_url}/tts/synthesize/stream"
        client = self._get_client()

        async def _gen() -> AsyncGenerator[bytes, None]:
            try:
                async with client.stream(
                    "POST", url, json=payload, timeout=self._timeout_s, headers=self._auth_headers()
                ) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes(chunk_size):
                        yield chunk
            except httpx.HTTPStatusError as exc:
                raise RemoteTTSError(
                    f"Remote TTS {url} returned HTTP {exc.response.status_code}"
                ) from exc
            except httpx.HTTPError as exc:
                raise RemoteTTSError(f"Remote TTS {url} unreachable: {exc}") from exc

        return _gen()

    async def stream_step(
        self,
        beats: list[dict],
        slots: dict[str, str] | None = None,
        interrupt: asyncio.Event | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """Stream a whole script step as one remote call (beats joined by pauses)."""
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
