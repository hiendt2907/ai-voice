"""STT via ElevenLabs Scribe v2.

Drop-in replacement for FasterWhisperSTT. Accepts PCM int16 bytes,
wraps them in a WAV container, and sends to the ElevenLabs /v1/speech-to-text
endpoint.

VAD architecture is unchanged — the caller accumulates frames until silence
is detected, then submits the complete utterance here.
"""

from __future__ import annotations

import io
import logging
import struct
import time
import wave

import httpx

from metrics.elevenlabs import record_request as _record_el
from stt.faster_whisper_stt import STTResult

logger = logging.getLogger(__name__)

_SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 8000, num_channels: int = 1, sampwidth: int = 2) -> bytes:
    """Wrap raw PCM int16 bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


class ElevenLabsSTT:
    """STT via ElevenLabs Scribe v2 — drop-in for FasterWhisperSTT.

    Args:
        api_key: ElevenLabs API key (shared with TTS key).
        language_code: BCP-47 language code; "vi" for Vietnamese.
                       Pass "auto" to let Scribe detect the language.
    """

    def __init__(self, api_key: str, language_code: str = "vi", redis: object | None = None) -> None:
        self._language_code = language_code
        self._redis = redis
        self._client = httpx.AsyncClient(
            headers={"xi-api-key": api_key},
            timeout=15.0,
        )
        logger.info("ElevenLabsSTT initialized (language=%s)", language_code)

    async def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 8000) -> STTResult:
        """Transcribe raw int16 PCM bytes → STTResult.

        Converts PCM to WAV in-memory, then POSTs to ElevenLabs Scribe v2.
        Returns empty STTResult if pcm_bytes is empty.
        """
        if not pcm_bytes:
            return STTResult(text="", confidence=0.0, is_final=True)

        wav_bytes = _pcm_to_wav(pcm_bytes, sample_rate=sample_rate)

        payload: dict[str, str] = {"model_id": "scribe_v2"}
        if self._language_code and self._language_code != "auto":
            payload["language_code"] = self._language_code

        t0 = time.monotonic()
        try:
            resp = await self._client.post(
                _SCRIBE_URL,
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data=payload,
            )
            resp.raise_for_status()
            latency_ms = (time.monotonic() - t0) * 1000
            await _record_el(self._redis, latency_ms=latency_ms, ok=True)
        except Exception:
            await _record_el(self._redis, latency_ms=None, ok=False)
            raise

        data = resp.json()

        text: str = data.get("text", "").strip()
        # Scribe does not return per-word confidence — use a fixed high value
        # when text is returned, 0 otherwise.
        confidence = 0.95 if text else 0.0
        detected_lang: str = data.get("language_code", self._language_code) or "vi"

        logger.debug("ElevenLabsSTT transcribed %d bytes → %r", len(pcm_bytes), text)
        return STTResult(text=text, confidence=confidence, is_final=True, language=detected_lang)

    async def aclose(self) -> None:
        await self._client.aclose()
