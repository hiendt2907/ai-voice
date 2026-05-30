"""G.711 μ-law ↔ PCM 16-bit 8kHz codec (pure numpy, no audioop).

audioop was removed in Python 3.13+. This implements the ITU-T G.711
μ-law encode/decode using vectorized numpy operations.
"""

from __future__ import annotations

import numpy as np

_ULAW_BIAS: int = 0x84   # 132
_ULAW_CLIP: int = 32635


def ulaw_to_pcm(ulaw_bytes: bytes) -> np.ndarray:
    """Decode 8-bit μ-law bytes → int16 PCM array at 8kHz.

    Matches the CPython audioop.ulaw2lin reference:
      t = ((mantissa << 3) + 132) << exponent
      sign=1 (positive PCM) → t - 132; sign=0 (negative PCM) → 132 - t
    """
    u = np.frombuffer(ulaw_bytes, dtype=np.uint8).astype(np.int32)
    u = ~u & 0xFF
    t = ((u & 0x0F) << 3) + _ULAW_BIAS
    t = t << ((u & 0x70) >> 4)
    return np.where(u & 0x80, t - _ULAW_BIAS, _ULAW_BIAS - t).astype(np.int16)


def pcm_to_ulaw(pcm_array: np.ndarray) -> bytes:
    """Encode int16 PCM array → 8-bit μ-law bytes."""
    samples = pcm_array.astype(np.int32)
    sign = np.where(samples >= 0, 0x80, 0)
    samples = np.where(samples >= 0, samples + _ULAW_BIAS, _ULAW_BIAS - samples)
    samples = np.minimum(samples, _ULAW_CLIP)

    # Highest set bit position in range [7..14] → exponent [0..7]
    exp = np.floor(np.log2(np.maximum(samples, 1))).astype(np.int32) - 7
    exp = np.clip(exp, 0, 7)

    mantissa = (samples >> (exp + 3)) & 0x0F
    ulaw = (~(sign | (exp << 4) | mantissa)).astype(np.uint8)
    return ulaw.tobytes()


def pcm_bytes_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """Convert raw int16 PCM bytes → float32 [-1.0, 1.0]."""
    return np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def float32_to_pcm_bytes(audio: np.ndarray) -> bytes:
    """Convert float32 [-1.0, 1.0] → raw int16 PCM bytes."""
    clipped = np.clip(audio, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()
