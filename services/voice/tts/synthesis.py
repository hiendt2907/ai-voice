"""TTS synthesis using gwen-tts (g-group-ai-lab/gwen-tts-0.6B).

Provides Vietnamese voice cloning via Qwen3-TTS finetuned model.
Output is 24kHz float32 WAV; resampled to 8kHz int16 PCM for telephony.

Reference voice: samples/voice/reference.wav + samples/voice/reference.txt
"""

from __future__ import annotations

import asyncio
import logging
from math import gcd
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MODEL_ID = "g-group-ai-lab/gwen-tts-0.6B"
_TARGET_SR = 8000  # telephony sample rate

_GENERATION_CONFIG = {
    "temperature": 0.3,
    "top_k": 20,
    "top_p": 0.9,
    "max_new_tokens": 4096,
    "repetition_penalty": 2.0,
    "subtalker_do_sample": True,
    "subtalker_temperature": 0.1,
    "subtalker_top_k": 20,
    "subtalker_top_p": 1.0,
}


def _resample_to_8k(audio: np.ndarray, orig_sr: int) -> np.ndarray:
    """Resample from orig_sr to 8kHz using polyphase anti-aliased resampling."""
    if orig_sr == _TARGET_SR:
        return audio
    g = gcd(orig_sr, _TARGET_SR)
    up = _TARGET_SR // g
    down = orig_sr // g
    return resample_poly(audio, up, down).astype(np.float32)


class GwenTTS:
    """Vietnamese TTS using gwen-tts-0.6B with voice cloning.

    Loads lazily on first call. Thread-safe via asyncio executor.
    """

    def __init__(
        self,
        model_id: str = _MODEL_ID,
        ref_audio_path: str | None = None,
        ref_text: str | None = None,
        device: str = "cpu",
    ) -> None:
        self._model_id = model_id
        self._device = device
        self._ref_audio_path = ref_audio_path or str(
            Path(__file__).parent.parent.parent.parent / "samples" / "voice" / "reference.wav"
        )
        self._ref_text = ref_text or _load_ref_text(self._ref_audio_path)
        self._model: object | None = None
        self._lock = asyncio.Lock()

    def _load_model(self) -> None:
        """Load gwen-tts model (blocking — run in executor)."""
        try:
            import torch
            from qwen_tts import Qwen3TTSModel  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "qwen-tts not installed. Run: uv add qwen-tts"
            ) from exc

        dtype = None
        try:
            import torch
            dtype = torch.bfloat16 if self._device != "cpu" else torch.float32
        except Exception:
            pass

        logger.info("Loading gwen-tts model %s on %s…", self._model_id, self._device)
        kwargs: dict = {"device_map": self._device}
        if dtype is not None:
            kwargs["dtype"] = dtype

        self._model = Qwen3TTSModel.from_pretrained(self._model_id, **kwargs)
        logger.info("gwen-tts model loaded.")

    def _synthesize_sync(self, text: str) -> bytes:
        """Synchronous synthesis → raw int16 PCM bytes at 8kHz."""
        if self._model is None:
            self._load_model()

        wavs, sr = self._model.generate_voice_clone(  # type: ignore[union-attr]
            text=text,
            language="Vietnamese",
            ref_audio=self._ref_audio_path,
            ref_text=self._ref_text,
            **_GENERATION_CONFIG,
        )
        audio = np.array(wavs[0], dtype=np.float32)
        audio_8k = _resample_to_8k(audio, sr)
        # Normalize and convert to int16
        peak = np.max(np.abs(audio_8k)) + 1e-8
        audio_8k = audio_8k / peak
        return (audio_8k * 32767).astype(np.int16).tobytes()

    async def synthesize(self, text: str) -> bytes:
        """Async synthesis → raw int16 PCM bytes at 8kHz."""
        loop = asyncio.get_event_loop()
        async with self._lock:
            return await loop.run_in_executor(None, self._synthesize_sync, text)

    async def stream_synthesize(self, text: str, chunk_ms: int = 20) -> "AsyncGenerator[bytes, None]":
        """Fake streaming: synthesize full utterance, then yield in 20ms chunks."""
        from collections.abc import AsyncGenerator  # noqa: PLC0415

        pcm = await self.synthesize(text)
        bytes_per_chunk = int(_TARGET_SR * chunk_ms / 1000) * 2  # int16 = 2 bytes

        async def _gen() -> AsyncGenerator[bytes, None]:
            for i in range(0, len(pcm), bytes_per_chunk):
                yield pcm[i : i + bytes_per_chunk]
                await asyncio.sleep(0)  # yield control

        return _gen()


def _load_ref_text(ref_audio_path: str) -> str:
    txt_path = Path(ref_audio_path).with_suffix(".txt")
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8").strip()
    return "Dạ Linh xin nghe ạ."
