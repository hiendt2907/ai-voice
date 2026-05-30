"""STT wrapper around faster-whisper.

Supports one-shot transcription and streaming accumulation mode.
Language is hardcoded to Vietnamese ("vi") for this deployment.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class STTResult:
    text: str
    confidence: float
    is_final: bool
    language: str = "vi"


class FasterWhisperSTT:
    """Wrapper around WhisperModel for Vietnamese transcription.

    Args:
        model_size: faster-whisper model size (tiny/base/small/medium/large-v3).
        device: 'cpu' or 'cuda'.
        compute_type: quantization type (int8, float16, etc.).
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        from faster_whisper import WhisperModel  # lazy import — large dep

        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("FasterWhisperSTT loaded: %s on %s (%s)", model_size, device, compute_type)

    def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 8000) -> STTResult:
        """Transcribe raw int16 PCM bytes → STTResult.

        Converts PCM to float32 WAV in-memory so faster-whisper can read it.
        """
        if not pcm_bytes:
            return STTResult(text="", confidence=0.0, is_final=True)

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="FLOAT")
        buf.seek(0)

        segments, info = self._model.transcribe(
            buf,
            language="vi",
            task="transcribe",
            beam_size=3,
            vad_filter=False,
        )

        texts: list[str] = []
        total_confidence = 0.0
        count = 0
        for seg in segments:
            texts.append(seg.text.strip())
            # faster-whisper exposes avg_logprob — convert to rough probability
            prob = float(np.exp(max(seg.avg_logprob, -5.0)))
            total_confidence += prob
            count += 1

        text = " ".join(t for t in texts if t)
        confidence = total_confidence / max(count, 1)
        return STTResult(text=text, confidence=confidence, is_final=True)
