"""SenseVoice STT wrapper — Vietnamese transcription + emotion detection.

Requires: uv sync --extra sensevoice (pulls funasr + torch ~1.5GB)
Model download on first run: ~500MB (iic/SenseVoiceSmall from HuggingFace)
"""

from __future__ import annotations

import logging
import re

import numpy as np

from stt.faster_whisper_stt import STTResult

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<\|([A-Z]+)\|>")
_STRIP_TAGS_RE = re.compile(r"<\|.*?\|>")

# SenseVoice emotion label → normalized lowercase
_EMOTION_MAP = {
    "HAPPY": "happy",
    "SAD": "sad",
    "ANGRY": "angry",
    "NEUTRAL": "neutral",
    "FEARFUL": "fearful",
    "DISGUSTED": "disgusted",
    "SURPRISED": "surprised",
}


class SenseVoiceSTT:
    """SenseVoice Small — sync transcription with emotion detection.

    Args:
        model_name: HuggingFace model ID (default iic/SenseVoiceSmall).
        device: "cpu" or "cuda:0".
        ban_emo_unk: Drop unknown emotion tag instead of returning None.
    """

    def __init__(
        self,
        model_name: str = "iic/SenseVoiceSmall",
        device: str = "cpu",
        ban_emo_unk: bool = True,
    ) -> None:
        try:
            from funasr import AutoModel  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "funasr is not installed. Run: uv sync --extra sensevoice"
            ) from exc

        self._ban_emo_unk = ban_emo_unk
        logger.info("Loading SenseVoice model: %s on %s", model_name, device)
        self._model = AutoModel(
            model=model_name,
            trust_remote_code=True,
            device=device,
        )
        logger.info("SenseVoiceSTT ready")

    def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 8000) -> STTResult:
        """Transcribe raw int16 PCM bytes → STTResult with emotion field."""
        if not pcm_bytes:
            return STTResult(text="", confidence=0.0, is_final=True)

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # SenseVoice requires 16kHz — resample from 8kHz
        if sample_rate != 16000:
            from scipy.signal import resample_poly  # noqa: PLC0415
            up = 16000 // sample_rate
            down = 1
            samples = resample_poly(samples, up, down).astype(np.float32)

        try:
            result = self._model.generate(
                input=samples,
                language="vi",
                use_itn=True,
                ban_emo_unk=self._ban_emo_unk,
            )
            raw_text: str = result[0]["text"] if result else ""
        except Exception as exc:
            logger.warning("SenseVoice generate error: %s", exc)
            return STTResult(text="", confidence=0.0, is_final=True)

        emotion = self._parse_emotion(raw_text)
        clean_text = _STRIP_TAGS_RE.sub("", raw_text).strip()

        return STTResult(
            text=clean_text,
            confidence=0.9,
            is_final=True,
            language="vi",
            emotion=emotion,
        )

    def _parse_emotion(self, raw_text: str) -> str | None:
        match = _TAG_RE.search(raw_text)
        if not match:
            return None
        label = match.group(1)
        return _EMOTION_MAP.get(label)
