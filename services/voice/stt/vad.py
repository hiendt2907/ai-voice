"""Voice Activity Detection — energy-based RMS by default, Silero VAD
(neural, ONNX) as an opt-in swap.

RMS: zero external deps, works immediately, but per
`docs/ai-streaming-voice-architecture-proposal.md` §D538/D989 has no
noise-floor adaptation and is not expected to survive a real phone line.
Silero: `stt/silero_vad.py`, canary-gated via `Settings.use_silero_vad`
(mirrors the `use_streaming_stt` rollout pattern) — same public interface,
so callers never need to know which backend is active.

Phase 5 additions:
  - min_speech_duration_ms: minimum accumulated speech before EOU is considered
    (prevents echo / noise triggering STT on fragments < 200ms)
  - half_duplex_suppress_ms: suppress barge-in detection for N ms after TTS starts
    (prevents TTS echo from triggering barge-in)
"""

from __future__ import annotations

import time

import numpy as np

_SILERO_THRESHOLD = 0.5  # Silero's own recommended speech-probability cutoff


class VADDetector:
    """VAD with end-of-utterance detection (RMS energy or Silero neural).

    Args:
        silence_threshold_ms: ms of silence to declare end-of-utterance.
        sample_rate: audio sample rate in Hz (default 8000).
        energy_threshold: RMS threshold for speech detection (0.0–1.0),
            used only when `use_silero=False`.
        frame_ms: frame duration used for analysis.
        min_speech_duration_ms: minimum speech duration before EOU is valid (Phase 5.3).
        half_duplex_suppress_ms: suppress barge-in for N ms after TTS starts (Phase 5.1).
        use_silero: use the neural Silero VAD (`stt/silero_vad.py`) instead
            of RMS energy. Frames are buffered internally to Silero's fixed
            window size (256 samples @ 8kHz / 512 @ 16kHz) — callers keep
            feeding arbitrary frame sizes exactly as with RMS.
    """

    def __init__(
        self,
        silence_threshold_ms: int = 400,
        sample_rate: int = 8000,
        energy_threshold: float = 0.01,
        frame_ms: int = 20,
        min_speech_duration_ms: int = 200,
        half_duplex_suppress_ms: int = 300,
        use_silero: bool = False,
    ) -> None:
        self._silence_threshold_ms = silence_threshold_ms
        self._sample_rate = sample_rate
        self._energy_threshold = energy_threshold
        self._frame_ms = frame_ms
        self._samples_per_frame = int(sample_rate * frame_ms / 1000)
        self._min_speech_duration_ms = min_speech_duration_ms
        self._half_duplex_suppress_ms = half_duplex_suppress_ms

        self._last_speech_ts: float | None = None
        self._speech_active: bool = False
        self._speech_start_ts: float | None = None
        self._tts_started_ts: float | None = None  # Phase 5.1: half-duplex gate

        self._silero: object | None = None
        self._silero_buffer = np.empty(0, dtype=np.int16)
        self._silero_last_prob = 0.0
        if use_silero:
            from stt.silero_vad import SileroVADModel  # noqa: PLC0415

            self._silero = SileroVADModel(sample_rate=sample_rate)

    def on_tts_start(self) -> None:
        """Call when TTS output begins — suppresses barge-in for half_duplex_suppress_ms (Phase 5.1)."""
        self._tts_started_ts = time.monotonic()

    def on_tts_end(self) -> None:
        """Call when TTS output finishes — removes half-duplex suppression."""
        self._tts_started_ts = None

    @property
    def is_half_duplex_suppressed(self) -> bool:
        """True during the half-duplex suppression window after TTS starts."""
        if self._tts_started_ts is None:
            return False
        elapsed_ms = (time.monotonic() - self._tts_started_ts) * 1000
        return elapsed_ms < self._half_duplex_suppress_ms

    def is_speech(self, frame_bytes: bytes) -> bool:
        """Return True if frame contains speech energy above threshold."""
        if len(frame_bytes) == 0:
            return False
        result = self._is_speech_silero(frame_bytes) if self._silero is not None else self._is_speech_rms(frame_bytes)
        if result:
            now = time.monotonic()
            if not self._speech_active:
                self._speech_start_ts = now
            self._last_speech_ts = now
            self._speech_active = True
        return result

    def _is_speech_rms(self, frame_bytes: bytes) -> bool:
        samples = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(samples**2)))
        return rms > self._energy_threshold

    def _is_speech_silero(self, frame_bytes: bytes) -> bool:
        assert self._silero is not None
        incoming = np.frombuffer(frame_bytes, dtype=np.int16)
        self._silero_buffer = np.concatenate([self._silero_buffer, incoming])

        window = self._silero.window_samples  # type: ignore[attr-defined]
        window_speech = False
        consumed_any_window = False
        while len(self._silero_buffer) >= window:
            consumed_any_window = True
            chunk, self._silero_buffer = self._silero_buffer[:window], self._silero_buffer[window:]
            self._silero_last_prob = self._silero.predict(chunk)  # type: ignore[attr-defined]
            if self._silero_last_prob > _SILERO_THRESHOLD:
                window_speech = True
        if not consumed_any_window:
            # Not enough buffered samples yet for a fresh window — fall back
            # to the last known probability instead of always reporting
            # silence, which would flap speech_active off between windows.
            return self._silero_last_prob > _SILERO_THRESHOLD
        return window_speech

    def _accumulated_speech_ms(self) -> float:
        """Return accumulated speech duration in ms since speech start."""
        if self._speech_start_ts is None or self._last_speech_ts is None:
            return 0.0
        return (self._last_speech_ts - self._speech_start_ts) * 1000

    def is_end_of_utterance(self) -> bool:
        """Return True when silence exceeds threshold after sufficient speech (Phase 5.3)."""
        if not self._speech_active or self._last_speech_ts is None:
            return False
        elapsed_ms = (time.monotonic() - self._last_speech_ts) * 1000
        if elapsed_ms < self._silence_threshold_ms:
            return False
        # Phase 5.3: reject micro-utterances (echo, noise) below min duration
        return self._accumulated_speech_ms() >= self._min_speech_duration_ms

    def reset(self) -> None:
        """Reset state for a new utterance."""
        self._last_speech_ts = None
        self._speech_active = False
        self._speech_start_ts = None

    @property
    def speech_active(self) -> bool:
        """True when speech energy has been detected — use for barge-in detection.

        Note: returns False during half-duplex suppression window to prevent
        TTS echo from triggering barge-in (Phase 5.1).
        """
        if self.is_half_duplex_suppressed:
            return False
        return self._speech_active
