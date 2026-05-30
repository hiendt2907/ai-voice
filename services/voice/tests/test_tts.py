"""Tests for Sprint 3: TTS fillers and audio stream."""

import asyncio

import numpy as np
import pytest

from tts.fillers import FillerSelector, _POOLS
from tts.prosody import PAUSE_DURATION_MS


# ---------------------------------------------------------------------------
# FillerSelector tests
# ---------------------------------------------------------------------------


def test_filler_selector_no_repeat():
    """Should not return the same filler twice in a row."""
    sel = FillerSelector()
    results = [sel.next("thinking") for _ in range(10)]
    for i in range(1, len(results)):
        assert results[i] != results[i - 1], f"Repeat at index {i}: {results[i]}"


def test_filler_selector_rotates():
    """Should cycle through all fillers in the pool."""
    sel = FillerSelector()
    pool = _POOLS["thinking"]
    seen = set()
    for _ in range(len(pool) * 2):
        seen.add(sel.next("thinking"))
    assert seen == set(pool)


def test_filler_selector_all_contexts():
    sel = FillerSelector()
    for ctx in ("thinking", "ack", "wait"):
        result = sel.next(ctx)  # type: ignore[arg-type]
        assert isinstance(result, str)
        assert len(result) > 0


def test_filler_selector_ack_no_repeat():
    sel = FillerSelector()
    prev = sel.next("ack")
    for _ in range(10):
        curr = sel.next("ack")
        assert curr != prev
        prev = curr


# ---------------------------------------------------------------------------
# Codec integration: silence has correct length
# ---------------------------------------------------------------------------


def test_silence_pcm_length():
    """20ms silence at 8kHz = 160 int16 samples = 320 bytes."""
    from tts.audio_stream import _silence_pcm  # noqa: PLC0415

    silence = _silence_pcm(20)
    n_samples = len(silence) // 2  # int16
    assert n_samples == 160, f"Expected 160 samples, got {n_samples}"
    # All zeros
    arr = np.frombuffer(silence, dtype=np.int16)
    assert np.all(arr == 0)


def test_silence_pcm_500ms():
    from tts.audio_stream import _silence_pcm  # noqa: PLC0415

    silence = _silence_pcm(500)
    n_samples = len(silence) // 2
    assert n_samples == 4000  # 500ms × 8000Hz


# ---------------------------------------------------------------------------
# BeatsAudioStream with mock TTS
# ---------------------------------------------------------------------------


class MockTTS:
    """Returns deterministic PCM bytes for given text."""

    async def synthesize(self, text: str) -> bytes:
        n = max(len(text) * 16, 160)
        return (np.zeros(n, dtype=np.int16) + 100).tobytes()

    async def stream_synthesize(self, text: str, chunk_ms: int = 20):
        pcm = await self.synthesize(text)
        chunk_size = 320  # 20ms at 8kHz

        async def _gen():
            for i in range(0, len(pcm), chunk_size):
                yield pcm[i : i + chunk_size]

        return _gen()


async def test_beats_audio_stream_yields_audio():
    from tts.audio_stream import BeatsAudioStream  # noqa: PLC0415

    beats = [
        {"text": "Xin chào bác.", "pause_after": "short"},
        {"text": "Em có thể giúp gì ạ?", "pause_after": "none"},
    ]
    tts = MockTTS()
    stream = BeatsAudioStream(tts)
    chunks = []
    async for chunk in stream.stream(beats):
        chunks.append(chunk)
    assert len(chunks) > 0
    total_bytes = sum(len(c) for c in chunks)
    assert total_bytes > 0


async def test_beats_audio_stream_respects_interrupt():
    from tts.audio_stream import BeatsAudioStream  # noqa: PLC0415

    interrupt = asyncio.Event()
    interrupt.set()  # already interrupted

    beats = [{"text": "Câu này không nên được phát.", "pause_after": "none"}]
    tts = MockTTS()
    stream = BeatsAudioStream(tts, interrupt)
    chunks = []
    async for chunk in stream.stream(beats):
        chunks.append(chunk)
    assert len(chunks) == 0  # interrupted immediately


async def test_beats_audio_stream_pause_inserted():
    from tts.audio_stream import BeatsAudioStream  # noqa: PLC0415

    beats = [{"text": "Một câu.", "pause_after": "short"}]
    tts = MockTTS()
    stream = BeatsAudioStream(tts)
    all_bytes = b""
    async for chunk in stream.stream(beats):
        all_bytes += chunk

    # Should include audio + 150ms silence (short = 150ms → 150×8=1200 samples → 2400 bytes)
    assert len(all_bytes) > 2400
