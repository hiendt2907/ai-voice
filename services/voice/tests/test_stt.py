"""Tests for Sprint 1: audio codec, VAD, STT."""

import struct
import time

import numpy as np
import pytest

from audio.codec import ulaw_to_pcm, pcm_to_ulaw, pcm_bytes_to_float32, float32_to_pcm_bytes
from stt.vad import VADDetector


# ---------------------------------------------------------------------------
# audio/codec tests
# ---------------------------------------------------------------------------


def _sine_pcm(freq: float = 440.0, sr: int = 8000, duration_s: float = 0.1) -> np.ndarray:
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    return (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)


def test_ulaw_roundtrip_silent():
    """Silent signal should roundtrip with low error."""
    zeros = np.zeros(160, dtype=np.int16)
    ulaw = pcm_to_ulaw(zeros)
    assert len(ulaw) == 160
    restored = ulaw_to_pcm(ulaw)
    assert len(restored) == 160
    # Silence should remain near-zero after codec roundtrip
    assert np.max(np.abs(restored.astype(np.int32))) < 200


def test_ulaw_roundtrip_sine():
    """Sine wave should roundtrip with reasonable SNR (μ-law is lossy but close)."""
    pcm = _sine_pcm()
    ulaw = pcm_to_ulaw(pcm)
    restored = ulaw_to_pcm(ulaw)
    assert len(ulaw) == len(pcm)
    assert len(restored) == len(pcm)
    # Check SNR: mean squared error should be much smaller than signal power
    mse = np.mean((pcm.astype(np.float32) - restored.astype(np.float32)) ** 2)
    signal_power = np.mean(pcm.astype(np.float32) ** 2)
    snr = signal_power / (mse + 1e-10)
    assert snr > 100, f"SNR too low: {snr:.1f}"


def test_float32_conversion_roundtrip():
    pcm = _sine_pcm()
    pcm_bytes = pcm.tobytes()
    f32 = pcm_bytes_to_float32(pcm_bytes)
    assert f32.dtype == np.float32
    assert np.max(np.abs(f32)) <= 1.0
    back = float32_to_pcm_bytes(f32)
    restored = np.frombuffer(back, dtype=np.int16)
    assert len(restored) == len(pcm)


def test_ulaw_to_pcm_all_bytes():
    """All 256 μ-law byte values should decode without error."""
    all_bytes = bytes(range(256))
    result = ulaw_to_pcm(all_bytes)
    assert len(result) == 256
    assert result.dtype == np.int16


# ---------------------------------------------------------------------------
# stt/vad tests
# ---------------------------------------------------------------------------


def _make_pcm_frame(rms_amplitude: float = 0.0, sr: int = 8000, duration_ms: int = 20) -> bytes:
    n = int(sr * duration_ms / 1000)
    if rms_amplitude == 0.0:
        return np.zeros(n, dtype=np.int16).tobytes()
    t = np.linspace(0, duration_ms / 1000, n, endpoint=False)
    signal = rms_amplitude * np.sin(2 * np.pi * 440 * t)
    return signal.astype(np.int16).tobytes()


def test_vad_detects_silence():
    vad = VADDetector(energy_threshold=0.01)
    frame = _make_pcm_frame(rms_amplitude=0.0)
    assert vad.is_speech(frame) is False
    assert vad.speech_active is False


def test_vad_detects_speech():
    vad = VADDetector(energy_threshold=0.01)
    # High amplitude frame — should be detected as speech
    pcm = (np.ones(160, dtype=np.int16) * 8000).tobytes()  # ~0.24 amplitude
    assert vad.is_speech(pcm) is True
    assert vad.speech_active is True


def test_vad_end_of_utterance():
    # min_speech_duration_ms=100 so even a short utterance passes
    vad = VADDetector(silence_threshold_ms=100, min_speech_duration_ms=100)
    pcm_speech = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    vad.is_speech(pcm_speech)
    assert vad.is_end_of_utterance() is False  # just spoke

    # Mock: 300ms of speech then 200ms of silence
    now = time.monotonic()
    vad._speech_start_ts = now - 0.5  # started 500ms ago
    vad._last_speech_ts = now - 0.2   # 200ms of silence
    assert vad.is_end_of_utterance() is True


def test_vad_reset():
    vad = VADDetector()
    pcm = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    vad.is_speech(pcm)
    assert vad.speech_active is True
    vad.reset()
    assert vad.speech_active is False
    assert vad._last_speech_ts is None


def test_vad_no_speech_no_eou():
    vad = VADDetector()
    assert vad.is_end_of_utterance() is False  # no speech ever


# ---------------------------------------------------------------------------
# Phase 5: half-duplex gate + min utterance duration
# ---------------------------------------------------------------------------


def test_vad_half_duplex_suppresses_speech_active():
    """Phase 5.1: speech_active returns False during half-duplex window."""
    vad = VADDetector(half_duplex_suppress_ms=300)
    pcm = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    vad.is_speech(pcm)  # mark speech active
    assert vad.speech_active is True  # before TTS

    vad.on_tts_start()
    assert vad.speech_active is False  # suppressed during TTS

    vad.on_tts_end()
    assert vad.speech_active is True  # restored after TTS ends


def test_vad_half_duplex_expires_after_window():
    """Phase 5.1: suppression ends after half_duplex_suppress_ms."""
    vad = VADDetector(half_duplex_suppress_ms=0)  # zero window → immediate release
    pcm = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    vad.is_speech(pcm)
    vad.on_tts_start()
    # With 0ms window, suppression is immediately expired
    assert not vad.is_half_duplex_suppressed
    assert vad.speech_active is True  # not suppressed


def test_vad_min_speech_duration_blocks_short_utterance():
    """Phase 5.3: utterance shorter than min_speech_duration_ms → no EOU."""
    vad = VADDetector(silence_threshold_ms=100, min_speech_duration_ms=200)
    pcm = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    vad.is_speech(pcm)
    # Simulate 150ms of speech (below min_speech_duration_ms=200ms)
    vad._speech_start_ts = time.monotonic() - 0.15
    vad._last_speech_ts = time.monotonic() - 0.11  # 110ms silence
    # EOU criteria: silence >= 100ms, but speech < 200ms → no EOU
    assert vad.is_end_of_utterance() is False


def test_vad_min_speech_duration_allows_long_utterance():
    """Phase 5.3: utterance longer than min_speech_duration_ms → EOU allowed."""
    vad = VADDetector(silence_threshold_ms=100, min_speech_duration_ms=200)
    pcm = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    vad.is_speech(pcm)
    # Simulate 300ms of speech then 150ms silence
    vad._speech_start_ts = time.monotonic() - 0.45
    vad._last_speech_ts = time.monotonic() - 0.15  # 150ms silence
    assert vad.is_end_of_utterance() is True


# ---------------------------------------------------------------------------
# Silero VAD (stt/silero_vad.py) — canary opt-in replacement for the RMS
# energy detector above, see docs/ai-streaming-voice-architecture-proposal.md
# D538/D989. Uses real recorded speech (bench/stt_audio/*.wav), not
# synthetic tones, since the whole point of swapping off RMS is behavior on
# real voice/noise that a constant-amplitude tone can't exercise.
# ---------------------------------------------------------------------------


def _wav_pcm(path: str) -> np.ndarray:
    import wave

    with wave.open(path, "rb") as wf:
        assert wf.getframerate() == 8000, "test WAV must already be 8kHz"
        raw = wf.readframes(wf.getnframes())
    return np.frombuffer(raw, dtype=np.int16)


def test_silero_vad_model_high_probability_on_real_speech():
    from stt.silero_vad import SileroVADModel

    model = SileroVADModel(sample_rate=8000)
    samples = _wav_pcm("bench/stt_audio/u01.wav")
    w = model.window_samples

    probs = [
        model.predict(samples[i : i + w]) for i in range(0, len(samples) - w + 1, w)
    ]

    assert max(probs) > 0.9, "no window in a real speech clip scored as confident speech"


def test_silero_vad_model_low_probability_on_silence():
    from stt.silero_vad import SileroVADModel

    model = SileroVADModel(sample_rate=8000)
    silence = np.zeros(model.window_samples, dtype=np.int16)

    assert model.predict(silence) < 0.5


def test_vad_detector_silero_backend_detects_real_speech_as_speech():
    """VADDetector(use_silero=True) — same public contract as the RMS
    backend (test_vad_detects_speech above), driven with real audio through
    the actual sliding-window buffering `is_speech()` does internally."""
    vad = VADDetector(sample_rate=8000, use_silero=True)
    samples = _wav_pcm("bench/stt_audio/u01.wav")
    frame = 160  # 20ms @ 8kHz, matches production audio_frame size

    detected_speech = any(
        vad.is_speech(samples[i : i + frame].tobytes())
        for i in range(0, len(samples) - frame + 1, frame)
    )

    assert detected_speech is True
    assert vad.speech_active is True


def test_vad_detector_silero_backend_silence_is_not_speech():
    vad = VADDetector(sample_rate=8000, use_silero=True)
    silence_frame = np.zeros(160, dtype=np.int16).tobytes()

    # Feed enough silent frames to fill at least one Silero window (256
    # samples @ 8kHz = 2 frames of 160) with margin.
    results = [vad.is_speech(silence_frame) for _ in range(5)]

    assert all(r is False for r in results)
    assert vad.speech_active is False


# ---------------------------------------------------------------------------
# STTResult emotion field (P2 — SenseVoice integration)
# ---------------------------------------------------------------------------

def test_stt_result_emotion_default_none():
    from stt.faster_whisper_stt import STTResult
    result = STTResult(text="hello", confidence=0.9, is_final=True)
    assert result.emotion is None


def test_stt_result_emotion_field():
    from stt.faster_whisper_stt import STTResult
    result = STTResult(text="hello", confidence=0.9, is_final=True, emotion="happy")
    assert result.emotion == "happy"
