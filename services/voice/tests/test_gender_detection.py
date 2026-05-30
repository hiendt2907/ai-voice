"""Tests for gender detection via F0 pitch analysis."""

from __future__ import annotations

import struct

import numpy as np
import pytest

from audio.gender import _autocorr_f0, _pcm_to_float, detect_gender


def _sine_pcm(freq_hz: float, duration_s: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Generate PCM bytes containing a pure sine wave at freq_hz."""
    n = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, n, endpoint=False)
    wave = (np.sin(2 * np.pi * freq_hz * t) * 16000).astype(np.int16)
    return struct.pack(f"<{n}h", *wave)


def test_detect_male_frequency():
    """120Hz sine → male"""
    pcm = _sine_pcm(120.0)
    result = detect_gender(pcm)
    assert result == "male"


def test_detect_female_frequency():
    """200Hz sine → female"""
    pcm = _sine_pcm(200.0)
    result = detect_gender(pcm)
    assert result == "female"


def test_detect_unknown_on_short_audio():
    result = detect_gender(b"\x00\x00" * 100)
    assert result == "unknown"


def test_detect_unknown_on_silence():
    pcm = b"\x00\x00" * 8000  # 0.5s silence at 16kHz
    result = detect_gender(pcm)
    assert result == "unknown"


def test_pcm_to_float_converts_correctly():
    samples = [0, 16384, -16384, 32767]
    raw = struct.pack(f"<{len(samples)}h", *samples)
    result = _pcm_to_float(raw)
    assert result is not None
    assert abs(result[0]) < 1e-6
    assert abs(result[1] - 0.5) < 0.01
    assert abs(result[2] + 0.5) < 0.01


def test_pcm_to_float_returns_none_on_empty():
    result = _pcm_to_float(b"")
    assert result is None


def test_autocorr_f0_returns_zero_on_silence():
    silence = np.zeros(512, dtype=np.float32)
    f0 = _autocorr_f0(silence, 16000, min_lag=53, max_lag=266)
    assert f0 == 0.0


def test_autocorr_f0_estimates_frequency():
    """Autocorrelation should recover ~120Hz from a clean sine."""
    freq = 120.0
    sr = 16000
    t = np.linspace(0, 512 / sr, 512, endpoint=False)
    frame = (np.sin(2 * np.pi * freq * t) * 0.5).astype(np.float32)
    min_lag = sr // 300
    max_lag = sr // 60
    f0 = _autocorr_f0(frame, sr, min_lag, max_lag)
    assert 100 <= f0 <= 140  # allow ±20Hz tolerance
