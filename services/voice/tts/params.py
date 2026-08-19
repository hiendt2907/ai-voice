"""TTS per-call parameters and emotion → TTS mapping."""

from __future__ import annotations

from dataclasses import dataclass

# (rate, stability, similarity_boost, style)
_EMOTION_TTS_MAP: dict[str, tuple[float, float, float, float]] = {
    "neutral":    (1.00, 0.50, 0.75, 0.20),
    "happy":      (1.10, 0.40, 0.75, 0.40),
    "frustrated": (0.88, 0.78, 0.80, 0.10),
    "confused":   (0.85, 0.70, 0.75, 0.10),
    "angry":      (0.75, 0.90, 0.80, 0.05),
    "sad":        (0.82, 0.80, 0.75, 0.05),
    "fearful":    (0.90, 0.70, 0.75, 0.05),
    "disgusted":  (0.85, 0.75, 0.75, 0.08),
    "surprised":  (1.05, 0.45, 0.75, 0.30),
}


@dataclass(frozen=True)
class TTSParams:
    speaking_rate: float = 1.0
    stability: float = 0.50
    similarity_boost: float = 0.75
    style: float = 0.20


@dataclass(frozen=True)
class EmotionState:
    label: str = "neutral"

    def to_tts_params(self, engine: str = "") -> TTSParams:
        """Map emotion label to TTS params.

        ElevenLabs: full mapping.
        edge-tts / local: only speaking_rate meaningful, rest use defaults.
        """
        rate, stab, sim, sty = _EMOTION_TTS_MAP.get(
            self.label, _EMOTION_TTS_MAP["neutral"]
        )
        if engine in ("edge-tts", "local", "gwen-tts", "kokoro"):
            return TTSParams(speaking_rate=rate)
        return TTSParams(speaking_rate=rate, stability=stab, similarity_boost=sim, style=sty)
