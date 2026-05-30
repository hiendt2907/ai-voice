"""Voice Activity Detection using energy-based RMS heuristics.

Primary: RMS energy threshold (zero external deps, works immediately).
Interface is designed so silero-vad can be plugged in as a drop-in
replacement when torch is available.

Phase 5 additions:
  - min_speech_duration_ms: minimum accumulated speech before EOU is considered
    (prevents echo / noise triggering STT on fragments < 200ms)
  - half_duplex_suppress_ms: suppress barge-in detection for N ms after TTS starts
    (prevents TTS echo from triggering barge-in)
"""

from __future__ import annotations

import time

import numpy as np


class VADDetector:
    """Energy-based VAD with end-of-utterance detection.

    Args:
        silence_threshold_ms: ms of silence to declare end-of-utterance.
        sample_rate: audio sample rate in Hz (default 8000).
        energy_threshold: RMS threshold for speech detection (0.0–1.0).
        frame_ms: frame duration used for analysis.
        min_speech_duration_ms: minimum speech duration before EOU is valid (Phase 5.3).
        half_duplex_suppress_ms: suppress barge-in for N ms after TTS starts (Phase 5.1).
    """

    def __init__(
        self,
        silence_threshold_ms: int = 400,
        sample_rate: int = 8000,
        energy_threshold: float = 0.01,
        frame_ms: int = 20,
        min_speech_duration_ms: int = 200,
        half_duplex_suppress_ms: int = 300,
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
        samples = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(samples**2)))
        result = rms > self._energy_threshold
        if result:
            now = time.monotonic()
            if not self._speech_active:
                self._speech_start_ts = now
            self._last_speech_ts = now
            self._speech_active = True
        return result

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
