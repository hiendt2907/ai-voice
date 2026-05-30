"""Gender detection via fundamental frequency (F0) analysis.

Female voices: F0 typically 165–255 Hz
Male voices:   F0 typically 85–165 Hz
Threshold:     165 Hz (ITU-T recommendation)

Input: raw PCM audio bytes (16-bit, 16kHz, mono)
"""

from __future__ import annotations

import struct
from typing import Literal

import numpy as np


_F0_THRESHOLD_HZ = 165.0
_FRAME_SIZE = 512   # ~32ms at 16kHz
_HOP_SIZE = 256


def detect_gender(pcm_bytes: bytes, sample_rate: int = 16000) -> Literal["male", "female", "unknown"]:
    """Estimate caller gender from PCM audio using zero-crossing rate as F0 proxy.

    For a quick, no-dependency estimate:
    - Compute mean F0 via autocorrelation on short frames
    - Below 165Hz → male, above → female
    """
    if len(pcm_bytes) < _FRAME_SIZE * 2:
        return "unknown"

    samples = _pcm_to_float(pcm_bytes)
    if samples is None or len(samples) < _FRAME_SIZE:
        return "unknown"

    f0_estimates = _estimate_f0_frames(samples, sample_rate)
    if not f0_estimates:
        return "unknown"

    median_f0 = float(np.median(f0_estimates))
    if median_f0 <= 0:
        return "unknown"

    return "female" if median_f0 >= _F0_THRESHOLD_HZ else "male"


def _pcm_to_float(pcm_bytes: bytes) -> np.ndarray | None:
    n_samples = len(pcm_bytes) // 2
    if n_samples == 0:
        return None
    fmt = f"<{n_samples}h"
    try:
        samples = struct.unpack(fmt, pcm_bytes[: n_samples * 2])
    except struct.error:
        return None
    return np.array(samples, dtype=np.float32) / 32768.0


def _estimate_f0_frames(samples: np.ndarray, sample_rate: int) -> list[float]:
    """Estimate F0 per frame using normalized autocorrelation."""
    f0s: list[float] = []
    num_frames = (len(samples) - _FRAME_SIZE) // _HOP_SIZE

    min_lag = sample_rate // 300  # 300Hz upper bound
    max_lag = sample_rate // 60   # 60Hz lower bound

    for i in range(num_frames):
        start = i * _HOP_SIZE
        frame = samples[start : start + _FRAME_SIZE]

        # Simple energy gate — skip silence
        if np.mean(np.abs(frame)) < 0.01:
            continue

        f0 = _autocorr_f0(frame, sample_rate, min_lag, max_lag)
        if f0 > 0:
            f0s.append(f0)

    return f0s


def _autocorr_f0(frame: np.ndarray, sample_rate: int, min_lag: int, max_lag: int) -> float:
    n = len(frame)
    autocorr = np.correlate(frame, frame, mode="full")[n - 1 :]
    if autocorr[0] < 1e-9:
        return 0.0
    autocorr /= autocorr[0]

    search = autocorr[min_lag : max_lag + 1]
    if len(search) == 0:
        return 0.0

    peak_lag = int(np.argmax(search)) + min_lag
    if autocorr[peak_lag] < 0.3:  # low confidence — treat as unvoiced
        return 0.0

    return float(sample_rate) / peak_lag
