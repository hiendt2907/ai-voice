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

# Biases decoding toward clinic vocabulary. Whisper conditions on this text as
# if it preceded the audio, so in-domain terms it would otherwise mangle become
# the likelier decode — "khám nội khoa" was coming back as "khám nội qua".
# Keep it short: the prompt competes with the audio for context, and a long one
# makes the model start echoing it.
_DOMAIN_PROMPT = (
    "Phòng khám DoctorCheck. Đặt lịch khám nội khoa, ngoại khoa, tai mũi họng, "
    "da liễu, tim mạch, sản phụ khoa, nhi khoa. Nội soi dạ dày, đại tràng. "
    "Khám tổng quát, xét nghiệm, siêu âm. Đặt lịch, hủy lịch, đổi giờ, "
    "kết quả xét nghiệm, bảo hiểm y tế."
)

# Whisper never returns "I heard nothing" — handed a segment that is mostly
# silence it emits its most likely *prior*, which for Vietnamese training data
# is YouTube subtitle boilerplate ("Hãy subscribe cho kênh Ghiền Mì Gõ…") or a
# regurgitation of `_DOMAIN_PROMPT`, and it reports those with ordinary
# confidence (0.69 observed), so a downstream confidence gate cannot catch
# them. Both were fed straight into the NLU as if the caller had said them.
#
# `no_speech_prob` is the honest signal but only at the extremes: a genuine
# 0.5-second reply ("Đúng rồi") is padded out to Whisper's 30-second window
# and comes back at 0.67, indistinguishable from a hallucination on that
# number alone. Dropping at 0.6 silently ate real answers and stalled the FSM.
# So gate only on values no real utterance produced (0.85+) and let the
# text-shape checks below catch what sits in the ambiguous middle.
_NO_SPEECH_MAX = 0.85
# A segment whose text is far more compressible than natural speech is the
# model stuck in a repetition loop ("nội khoa, nhi khoa, nhi khoa, nhi khoa").
_COMPRESSION_RATIO_MAX = 2.4
# Below this average log-probability the decode is guesswork, not a transcript.
_LOG_PROB_MIN = -1.0


# Fixed phrases Whisper emits from its Vietnamese YouTube-subtitle prior when
# a segment carries no speech. They are model artifacts, not clinic language —
# no caller phoning a clinic asks anyone to subscribe to a channel — so
# matching them by text is safe and catches the cases that sit below the
# no_speech_prob cutoff. Match is on a lowercased substring, so inflected
# variants of the same boilerplate are covered by their distinctive fragment.
_BOILERPLATE_FRAGMENTS = (
    "subscribe",
    "ghiền mì gõ",
    "đăng ký kênh",
    "cảm ơn các bạn đã theo dõi",
    "cảm ơn các bạn đã xem",
    "cảm ơn các bạn.",
    "hẹn gặp lại các bạn",
    "video tiếp theo",
    "like và đăng ký",
    "bấm chuông thông báo",
)


def _is_boilerplate(text: str) -> bool:
    lowered = text.strip().lower()
    return any(frag in lowered for frag in _BOILERPLATE_FRAGMENTS)


def _is_repetition_loop(text: str, min_repeats: int = 3) -> bool:
    """True when the same short phrase repeats back-to-back.

    `compression_ratio` only catches a runaway loop once it has run long
    enough; the short ones survive it ("ngoại khoa, nhi khoa, nhi khoa, nhi
    khoa") and read to the NLU as a plausible in-domain utterance, which is
    worse than nonsense — it matched book_appointment at 0.68 and pushed the
    FSM forward on something the caller never said. No caller says the same
    two words three times in a row, so the pattern itself is the signal.
    """
    words = [w for w in text.lower().replace(",", " ").split() if w]
    for size in (1, 2, 3):
        run = 1
        for i in range(size, len(words) - size + 1, size):
            if words[i : i + size] == words[i - size : i]:
                run += 1
                if run >= min_repeats:
                    return True
            else:
                run = 1
    return False


def _is_hallucination(seg: object) -> bool:
    """True when Whisper's own per-segment diagnostics say this text was
    invented rather than heard.

    `transcribe()`'s thresholds only gate *whole temperature fallbacks*; a
    segment that trips them can still be returned. Re-checking them here is
    what actually keeps the text out of the transcript.
    """
    if float(getattr(seg, "no_speech_prob", 0.0)) > _NO_SPEECH_MAX:
        return True
    if float(getattr(seg, "compression_ratio", 0.0)) > _COMPRESSION_RATIO_MAX:
        return True
    if float(getattr(seg, "avg_logprob", 0.0)) < _LOG_PROB_MIN:
        return True
    text = str(getattr(seg, "text", ""))
    return _is_boilerplate(text) or _is_repetition_loop(text)


@dataclass(frozen=True)
class STTResult:
    text: str
    confidence: float
    is_final: bool
    language: str = "vi"
    emotion: str | None = None


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
        num_workers: int = 1,
    ) -> None:
        """`num_workers` is CTranslate2's internal concurrency limit for this
        model instance (default 1, matching faster-whisper's own default).
        With num_workers=1, two concurrent `transcribe()` calls from
        different Python threads do NOT run in parallel — the second blocks
        inside CT2 until the first finishes, regardless of how many threads
        or executors dispatch them. The streaming STT gateway (`/ws/stt` in
        `inference_server.py`) needs num_workers >= 2 so a `stt.final`
        decode is never serialized behind an in-flight `stt.partial`
        re-decode (see the fix for that in `inference_server.py`)."""
        from faster_whisper import WhisperModel  # lazy import — large dep

        self._model = WhisperModel(
            model_size, device=device, compute_type=compute_type, num_workers=num_workers
        )
        logger.info(
            "FasterWhisperSTT loaded: %s on %s (%s, num_workers=%d)",
            model_size, device, compute_type, num_workers,
        )

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
            initial_prompt=_DOMAIN_PROMPT,
            # Each utterance is decoded independently; carrying the previous
            # decode in as context is what lets a single bad turn seed a
            # repetition loop for the rest of the call.
            condition_on_previous_text=False,
            no_speech_threshold=_NO_SPEECH_MAX,
            log_prob_threshold=_LOG_PROB_MIN,
            compression_ratio_threshold=_COMPRESSION_RATIO_MAX,
        )

        texts: list[str] = []
        total_confidence = 0.0
        count = 0
        for seg in segments:
            if _is_hallucination(seg):
                logger.info(
                    "Dropping hallucinated STT segment (no_speech_prob=%.2f "
                    "compression_ratio=%.2f avg_logprob=%.2f): %r",
                    getattr(seg, "no_speech_prob", 0.0),
                    getattr(seg, "compression_ratio", 0.0),
                    getattr(seg, "avg_logprob", 0.0),
                    seg.text.strip(),
                )
                continue
            texts.append(seg.text.strip())
            # faster-whisper exposes avg_logprob — convert to rough probability
            prob = float(np.exp(max(seg.avg_logprob, -5.0)))
            total_confidence += prob
            count += 1

        text = " ".join(t for t in texts if t)
        confidence = total_confidence / max(count, 1)
        return STTResult(text=text, confidence=confidence, is_final=True)
