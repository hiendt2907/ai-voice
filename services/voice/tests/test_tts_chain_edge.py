"""Tests for TTSChain, EdgeTTS to push coverage above 80%."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tts.chain import CircuitBreaker, ElevenLabsQuotaTracker, QuotaExceededError, TTSChain
from tts.params import TTSParams


# ── EdgeTTS ──────────────────────────────────────────────────────────────────


def test_edge_tts_effective_rate_default():
    from tts.edge_tts import EdgeTTS
    e = EdgeTTS()
    assert e._effective_rate(None) == "+0%"


def test_edge_tts_effective_rate_fast():
    from tts.edge_tts import EdgeTTS
    e = EdgeTTS()
    rate = e._effective_rate(TTSParams(speaking_rate=1.10))
    assert rate == "+10%"


def test_edge_tts_effective_rate_slow():
    from tts.edge_tts import EdgeTTS
    e = EdgeTTS()
    rate = e._effective_rate(TTSParams(speaking_rate=0.88))
    assert rate == "-12%"


def test_edge_tts_effective_rate_neutral():
    from tts.edge_tts import EdgeTTS
    e = EdgeTTS()
    rate = e._effective_rate(TTSParams(speaking_rate=1.0))
    assert rate == "+0%"


@pytest.mark.asyncio
async def test_edge_tts_synthesize_with_params():
    from tts.edge_tts import EdgeTTS
    e = EdgeTTS()
    with patch("tts.edge_tts.asyncio.to_thread", new_callable=AsyncMock, return_value=b"") as mock_thread:
        result = await e.synthesize("test", TTSParams(speaking_rate=0.8))
        assert result == b""
        # asyncio.to_thread(func, text, voice, rate) — rate is [3]
        call_args = mock_thread.call_args[0]
        assert call_args[3] == "-20%"


@pytest.mark.asyncio
async def test_edge_tts_stream_synthesize_yields_chunk():
    from tts.edge_tts import EdgeTTS
    e = EdgeTTS()
    with patch.object(e, "synthesize", new_callable=AsyncMock, return_value=b"pcm_data"):
        gen = await e.stream_synthesize("hello", None)
        chunks = [chunk async for chunk in gen]
        assert chunks == [b"pcm_data"]


@pytest.mark.asyncio
async def test_edge_tts_stream_synthesize_empty():
    from tts.edge_tts import EdgeTTS
    e = EdgeTTS()
    with patch.object(e, "synthesize", new_callable=AsyncMock, return_value=b""):
        gen = await e.stream_synthesize("hello", None)
        chunks = [chunk async for chunk in gen]
        assert chunks == []


# ── ElevenLabsQuotaTracker ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quota_tracker_unlimited():
    mock_redis = AsyncMock()
    tracker = ElevenLabsQuotaTracker(redis=mock_redis, daily_cap=0)
    # Should not raise even without redis call
    await tracker.count_chars(10000)
    mock_redis.incrby.assert_not_called()


@pytest.mark.asyncio
async def test_quota_tracker_under_cap():
    mock_redis = AsyncMock()
    mock_redis.incrby = AsyncMock(return_value=100)
    mock_redis.expire = AsyncMock()
    tracker = ElevenLabsQuotaTracker(redis=mock_redis, daily_cap=1000)
    await tracker.count_chars(100)  # should not raise


@pytest.mark.asyncio
async def test_quota_tracker_over_cap():
    mock_redis = AsyncMock()
    mock_redis.incrby = AsyncMock(return_value=1001)
    mock_redis.expire = AsyncMock()
    tracker = ElevenLabsQuotaTracker(redis=mock_redis, daily_cap=1000)
    with pytest.raises(QuotaExceededError):
        await tracker.count_chars(100)


@pytest.mark.asyncio
async def test_quota_tracker_status_unlimited():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    tracker = ElevenLabsQuotaTracker(redis=mock_redis, daily_cap=0)
    status = await tracker.status()
    assert status["cap"] == 0
    assert status["remaining"] == -1


@pytest.mark.asyncio
async def test_quota_tracker_status_with_cap():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="500")
    tracker = ElevenLabsQuotaTracker(redis=mock_redis, daily_cap=1000)
    status = await tracker.status()
    assert status["used"] == 500
    assert status["remaining"] == 500


# ── TTSChain ─────────────────────────────────────────────────────────────────


def make_mock_engine(audio: bytes = b"audio", should_fail: bool = False):
    engine = MagicMock()
    if should_fail:
        engine.synthesize = AsyncMock(side_effect=RuntimeError("engine failed"))
        engine.stream_synthesize = AsyncMock(side_effect=RuntimeError("engine failed"))
    else:
        engine.synthesize = AsyncMock(return_value=audio)

        async def _stream_gen():
            yield audio

        async def _stream_synthesize(text, params=None):
            return _stream_gen()

        engine.stream_synthesize = _stream_synthesize
    return engine


@pytest.mark.asyncio
async def test_tts_chain_primary_engine():
    mock_redis = AsyncMock()
    cb = CircuitBreaker()
    tracker = ElevenLabsQuotaTracker(mock_redis, daily_cap=0)
    engine = make_mock_engine(b"audio1")
    chain = TTSChain([engine], ["edge-tts"], cb, tracker)
    assert chain.primary_engine_name() == "edge-tts"


@pytest.mark.asyncio
async def test_tts_chain_synthesize_success():
    mock_redis = AsyncMock()
    cb = CircuitBreaker()
    tracker = ElevenLabsQuotaTracker(mock_redis, daily_cap=0)
    engine = make_mock_engine(b"pcm_data")
    chain = TTSChain([engine], ["edge-tts"], cb, tracker)
    result = await chain.synthesize("hello", None)
    assert result == b"pcm_data"


@pytest.mark.asyncio
async def test_tts_chain_fallback_on_failure():
    mock_redis = AsyncMock()
    cb = CircuitBreaker(threshold=1)
    tracker = ElevenLabsQuotaTracker(mock_redis, daily_cap=0)
    failing_engine = make_mock_engine(should_fail=True)
    good_engine = make_mock_engine(b"fallback_audio")
    chain = TTSChain([failing_engine, good_engine], ["elevenlabs", "edge-tts"], cb, tracker)
    result = await chain.synthesize("hello", None)
    assert result == b"fallback_audio"
    assert cb.is_open("elevenlabs")


@pytest.mark.asyncio
async def test_tts_chain_all_fail_raises():
    mock_redis = AsyncMock()
    cb = CircuitBreaker(threshold=1)
    tracker = ElevenLabsQuotaTracker(mock_redis, daily_cap=0)
    failing = make_mock_engine(should_fail=True)
    chain = TTSChain([failing], ["elevenlabs"], cb, tracker)
    with pytest.raises(RuntimeError):
        await chain.synthesize("hello", None)


@pytest.mark.asyncio
async def test_tts_chain_stream_synthesize():
    mock_redis = AsyncMock()
    cb = CircuitBreaker()
    tracker = ElevenLabsQuotaTracker(mock_redis, daily_cap=0)
    engine = make_mock_engine(b"chunk1")
    chain = TTSChain([engine], ["edge-tts"], cb, tracker)
    gen = await chain.stream_synthesize("hello", None)
    chunks = [c async for c in gen]
    assert chunks == [b"chunk1"]


@pytest.mark.asyncio
async def test_tts_chain_engine_status():
    mock_redis = AsyncMock()
    cb = CircuitBreaker(threshold=1)
    tracker = ElevenLabsQuotaTracker(mock_redis, daily_cap=0)
    engine = make_mock_engine(should_fail=True)
    chain = TTSChain([engine], ["elevenlabs"], cb, tracker)
    with pytest.raises(RuntimeError):
        await chain.synthesize("fail", None)
    status = chain.engine_status()
    assert status["elevenlabs"] == "open"


@pytest.mark.asyncio
async def test_tts_chain_skip_open_circuit():
    mock_redis = AsyncMock()
    cb = CircuitBreaker(threshold=1)
    cb.record_failure("elevenlabs")  # opens circuit immediately (threshold=1)
    tracker = ElevenLabsQuotaTracker(mock_redis, daily_cap=0)
    good_engine = make_mock_engine(b"ok")
    bad_engine = make_mock_engine(b"bad", should_fail=True)
    chain = TTSChain([bad_engine, good_engine], ["elevenlabs", "edge-tts"], cb, tracker)
    result = await chain.synthesize("hello", None)
    assert result == b"ok"
    bad_engine.synthesize.assert_not_called()


@pytest.mark.asyncio
async def test_tts_chain_quota_exceeded_fallback():
    mock_redis = AsyncMock()
    mock_redis.incrby = AsyncMock(return_value=1001)
    mock_redis.expire = AsyncMock()
    cb = CircuitBreaker()
    tracker = ElevenLabsQuotaTracker(mock_redis, daily_cap=1000)
    elevenlabs_engine = make_mock_engine(b"el_audio")
    edge_engine = make_mock_engine(b"edge_audio")
    chain = TTSChain([elevenlabs_engine, edge_engine], ["elevenlabs", "edge-tts"], cb, tracker)
    result = await chain.synthesize("hello", None)
    assert result == b"edge_audio"
    elevenlabs_engine.synthesize.assert_not_called()  # quota exceeded before call
