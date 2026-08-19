"""Filler word pools for Vietnamese AI call agent.

Fillers are short utterances played immediately after speech detection to
reduce perceived latency while processing is happening concurrently.

Anti-repetition: FillerSelector rotates through the pool, never repeating
the same filler twice in a row.

Pre-recorded audio: FillerSelector.next_audio() returns pre-synthesized PCM
bytes (int16, 8kHz) loaded from tts/filler_audio/<context>/<hash>.wav.
Falls back to None if files are missing — caller should synthesize on the fly.

Context types:
  thinking   — very short, while STT+intent finishes (<300ms processing)
  ack        — acknowledgment when intent matched with no slot fill
  wait       — generic wait (longer processing)
  checking   — actively looking up data (API call in progress)
  confirming — confirming/booking action in progress
  ack_slot   — echo back the slot value just heard (use value= param)
  calming    — calm an agitated caller
  deescalate — de-escalate an angry caller
  clarifying — ask caller to clarify
"""

from __future__ import annotations

import hashlib
import logging
import wave
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

ContextType = Literal[
    "thinking", "ack", "wait", "checking", "confirming",
    "ack_slot", "calming", "deescalate", "clarifying",
]

_POOLS: dict[ContextType, list[str]] = {
    "thinking": [
        "Dạ,",
        "Vâng ạ,",
        "À,",
        "Ừm,",
        "Được ạ,",
        "Dạ vâng,",
    ],
    "ack": [
        "Dạ vâng, em ghi nhận rồi ạ.",
        "Được ạ, em hiểu rồi.",
        "Vâng, em nhận thông tin rồi ạ.",
        "Dạ, anh/chị yên tâm ạ.",
        "Em hiểu ý anh/chị rồi ạ.",
    ],
    "wait": [
        "Dạ, bác đợi em một chút nhé ạ.",
        "Em xem ngay cho anh/chị ạ.",
        "Vâng, để em kiểm tra lại một chút ạ.",
        "Anh/chị đợi em một chút được không ạ?",
        "Dạ, em tra cứu ngay ạ.",
    ],
    "checking": [
        "Dạ, để em xem lịch cho anh/chị nhé...",
        "Vâng, em kiểm tra hệ thống ngay ạ...",
        "Dạ, cho em xem thông tin một chút ạ...",
        "Em đang tra lịch khám cho anh/chị ạ...",
        "Vâng, để em vào hệ thống xem giúp ạ...",
    ],
    "confirming": [
        "Dạ, để em xác nhận lại thông tin cho anh/chị ạ...",
        "Vâng, em đặt lịch cho anh/chị ngay ạ...",
        "Dạ, em đang xử lý yêu cầu của anh/chị ạ...",
        "Để em lưu thông tin lại cho anh/chị nhé...",
    ],
    "ack_slot": [
        "Vâng, {value} ạ.",
        "Dạ, {value} ạ.",
        "À vâng, {value} ạ.",
        "Em ghi nhận {value} rồi ạ.",
    ],
    "calming": [
        "Dạ, anh/chị cứ từ từ ạ, em lắng nghe ạ.",
        "Vâng, không sao ạ, anh/chị nói từ từ nhé.",
        "Dạ em hiểu ạ, anh/chị yên tâm ạ.",
        "Anh/chị nói chậm thôi cũng được ạ.",
    ],
    "deescalate": [
        "Dạ, em rất xin lỗi vì sự bất tiện này ạ.",
        "Vâng, em hiểu anh/chị đang không hài lòng, em sẽ cố hết sức hỗ trợ ạ.",
        "Dạ, bác thông cảm cho em với ạ, em sẽ giải quyết ngay ạ.",
        "Em xin lỗi ạ, để em hỗ trợ anh/chị ngay ạ.",
    ],
    "clarifying": [
        "Dạ, để em xác nhận lại cho chắc ạ.",
        "Vâng, bác cho em hỏi thêm một chút được không ạ?",
        "Dạ, ý anh/chị là... em hiểu đúng không ạ?",
        "Để em nắm rõ hơn, anh/chị có thể nói lại được không ạ?",
    ],
}

_AUDIO_DIR = Path(__file__).parent / "filler_audio"

# 350ms silence at 8kHz int16 — natural pause between filler and main TTS response
_FILLER_TRAILING_SILENCE = b"\x00" * (8000 * 2 * 350 // 1000)


def _wav_to_pcm(path: Path) -> bytes:
    """Read WAV file → raw int16 PCM bytes."""
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


def _build_audio_cache() -> dict[str, bytes]:
    """Pre-load all filler WAV files into memory on import."""
    cache: dict[str, bytes] = {}
    if not _AUDIO_DIR.exists():
        logger.warning("Filler audio dir not found: %s — will synthesize on the fly", _AUDIO_DIR)
        return cache
    for wav_path in _AUDIO_DIR.rglob("*.wav"):
        try:
            cache[wav_path.stem] = _wav_to_pcm(wav_path)
        except Exception as exc:
            logger.warning("Failed to load filler WAV %s: %s", wav_path.name, exc)
    logger.info("Filler audio cache loaded: %d pre-recorded files from %s", len(cache), _AUDIO_DIR)
    return cache


_AUDIO_CACHE: dict[str, bytes] = _build_audio_cache()


class FillerSelector:
    """Stateful filler selector with anti-repetition.

    next_audio() returns pre-recorded PCM bytes + trailing silence for
    seamless transition into the main TTS response.
    Falls back to next() (text) when no audio file is available.
    """

    def __init__(self) -> None:
        self._last: dict[ContextType, str] = {}
        self._indices: dict[str, int] = {k: 0 for k in _POOLS}

    def next_for_emotion(self, emotion_label: str) -> str:
        pool_map: dict[str, ContextType] = {
            "angry": "deescalate",
            "frustrated": "calming",
            "confused": "clarifying",
        }
        ctx: ContextType = pool_map.get(emotion_label, "thinking")
        return self.next(ctx)

    def next(self, context: ContextType = "thinking", value: str = "") -> str:
        """Return next filler text for the given context."""
        pool = _POOLS[context]
        last = self._last.get(context)
        idx = self._indices.get(context, 0)

        for _ in range(len(pool)):
            candidate = pool[idx % len(pool)]
            idx += 1
            if candidate != last:
                self._indices[context] = idx
                self._last[context] = candidate
                result = candidate.replace("{value}", value) if value else candidate
                return result

        result = pool[0].replace("{value}", value) if value else pool[0]
        return result

    def next_audio(
        self, context: ContextType = "thinking", value: str = ""
    ) -> tuple[str, bytes | None]:
        """Return (filler_text, pcm_bytes_or_None).

        pcm_bytes includes trailing 100ms silence for smooth transition.
        Returns None for pcm when audio file is unavailable (caller should synthesize).
        """
        text = self.next(context, value)
        if "{value}" in text or not _AUDIO_CACHE:
            return text, None

        key = hashlib.md5(text.encode()).hexdigest()[:8]
        pcm = _AUDIO_CACHE.get(key)
        if pcm is None:
            logger.debug("Filler cache miss for '%s' (key=%s) — will synthesize", text[:30], key)
            return text, None
        logger.debug("Filler cache hit: '%s' (%d bytes + 350ms silence)", text[:30], len(pcm))
        return text, pcm + _FILLER_TRAILING_SILENCE

    def next_audio_for_emotion(self, emotion_label: str) -> tuple[str, bytes | None]:
        pool_map: dict[str, ContextType] = {
            "angry": "deescalate",
            "frustrated": "calming",
            "confused": "clarifying",
        }
        ctx: ContextType = pool_map.get(emotion_label, "thinking")
        return self.next_audio(ctx)
