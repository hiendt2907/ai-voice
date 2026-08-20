"""Local TTS using Piper (ONNX) — fully offline, ~30-50ms after warm-up.

Model: vi_VN-vais1000-medium (60MB, 22050Hz, single speaker)
Output: int16 PCM at 8kHz (telephony standard)

Uses a module-level singleton so the ONNX model is loaded once and shared
across all sessions. First synthesis: ~300ms (ONNX JIT). Subsequent: ~30-50ms.
"""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = str(
    Path(__file__).parent.parent / "models" / "piper" / "vi_VN-vais1000-medium.onnx"
)
_TARGET_SR = 8000

# Module-level singleton — shared across all PiperTTS instances / sessions
_voice_singleton: object | None = None
_voice_sr: int = 22050
_voice_lock = asyncio.Lock()


def _load_voice(model_path: str) -> tuple[object, int]:
    """Load Piper model (blocking). Returns (voice, sample_rate)."""
    global _voice_singleton, _voice_sr
    if _voice_singleton is not None:
        return _voice_singleton, _voice_sr
    from piper import PiperVoice  # noqa: PLC0415
    logger.info("Loading Piper model %s …", model_path)
    _voice_singleton = PiperVoice.load(model_path)
    _voice_sr = _voice_singleton.config.sample_rate  # type: ignore[union-attr]
    logger.info("Piper model loaded (sr=%dHz)", _voice_sr)
    return _voice_singleton, _voice_sr


class PiperTTS:
    """Piper ONNX TTS — local, free, Vietnamese.

    Shares the loaded model across all instances via module-level singleton.
    Thread-safe via asyncio executor.
    """

    def __init__(self, model_path: str = _DEFAULT_MODEL) -> None:
        self._model_path = model_path

    def _synthesize_sync(self, text: str) -> bytes:
        voice, sr = _load_voice(self._model_path)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_f:
            voice.synthesize_wav(text, wav_f)  # type: ignore[union-attr]
        buf.seek(0)
        with wave.open(buf) as wav_f:
            raw = wav_f.readframes(wav_f.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return _resample(samples, sr)

    async def synthesize(self, text: str, _params: object = None) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text)

    async def stream_synthesize(self, text: str, chunk_ms: int = 20):
        """True streaming: yields one chunk per SENTENCE as Piper's own
        `synthesize()` generator produces it, instead of the previous
        pseudo-stream (synthesize the whole utterance via `synthesize_wav`,
        then slice the finished buffer into fixed-size pieces — TTFA was
        ~96% of total synthesis time, see
        docs/ai-streaming-voice-architecture-proposal.md §1182/§197).
        Multi-sentence beats now get audio for sentence 1 while sentence 2+
        are still being synthesized, same as a real streaming engine.
        """
        voice, _ = _load_voice(self._model_path)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue()

        def _produce() -> None:
            try:
                for chunk in voice.synthesize(text):  # type: ignore[union-attr]
                    samples = (
                        np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16).astype(np.float32)
                        / 32768.0
                    )
                    pcm = _resample(samples, chunk.sample_rate)
                    loop.call_soon_threadsafe(queue.put_nowait, pcm)
            except BaseException as exc:  # noqa: BLE001 — relayed to the consumer below
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        async def _gen():
            producer = loop.run_in_executor(None, _produce)
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        return
                    if isinstance(item, BaseException):
                        raise item
                    yield item
            finally:
                await producer

        return _gen()

    async def warmup(self) -> None:
        """Pre-load model and JIT-compile ONNX graph (eliminates first-call 300ms)."""
        await self.synthesize("Xin chào.")
        logger.info("Piper TTS warmed up.")


def _resample(audio: np.ndarray, from_sr: int) -> bytes:
    if from_sr == _TARGET_SR:
        return (audio * 32767).astype(np.int16).tobytes()
    g = gcd(from_sr, _TARGET_SR)
    resampled = resample_poly(audio, _TARGET_SR // g, from_sr // g)
    peak = np.max(np.abs(resampled)) + 1e-8
    return ((resampled / peak) * 32767).astype(np.int16).tobytes()
