"""Tests for ElevenLabs metrics module.

Uses unittest.mock for AsyncMock Redis — no real Redis needed.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metrics.elevenlabs import (
    REDIS_HASH_KEY,
    KEY_TOTAL,
    KEY_OK,
    KEY_ERR,
    KEY_LATENCY_SUM,
    KEY_LAST_SUCCESS_TS,
    record_request,
)


@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.hincrbyfloat = AsyncMock(return_value=1)
    return redis


@pytest.mark.asyncio
async def test_record_ok_increments_total_and_ok(mock_redis: AsyncMock) -> None:
    await record_request(mock_redis, latency_ms=120.5, ok=True)

    calls = {call.args[1]: call.args[2] for call in mock_redis.hincrbyfloat.call_args_list}
    assert calls[KEY_TOTAL] == 1
    assert calls[KEY_OK] == 1
    assert KEY_ERR not in calls
    assert calls[KEY_LATENCY_SUM] == pytest.approx(120.5)


@pytest.mark.asyncio
async def test_record_ok_sets_last_success_ts(mock_redis: AsyncMock) -> None:
    before = time.time() * 1000
    await record_request(mock_redis, latency_ms=50.0, ok=True)
    after = time.time() * 1000

    mock_redis.hset.assert_called_once()
    args = mock_redis.hset.call_args
    stored_ts = float(args.kwargs["mapping"][KEY_LAST_SUCCESS_TS])
    assert before <= stored_ts <= after


@pytest.mark.asyncio
async def test_record_err_increments_total_and_err(mock_redis: AsyncMock) -> None:
    await record_request(mock_redis, latency_ms=None, ok=False)

    calls = {call.args[1]: call.args[2] for call in mock_redis.hincrbyfloat.call_args_list}
    assert calls[KEY_TOTAL] == 1
    assert calls[KEY_ERR] == 1
    assert KEY_OK not in calls
    assert KEY_LATENCY_SUM not in calls


@pytest.mark.asyncio
async def test_record_err_does_not_set_last_success_ts(mock_redis: AsyncMock) -> None:
    await record_request(mock_redis, latency_ms=None, ok=False)
    mock_redis.hset.assert_not_called()


@pytest.mark.asyncio
async def test_redis_error_does_not_raise(mock_redis: AsyncMock) -> None:
    """Metrics recording is best-effort — Redis failure must not propagate."""
    mock_redis.hincrbyfloat.side_effect = Exception("Redis connection lost")
    # Should NOT raise
    await record_request(mock_redis, latency_ms=80.0, ok=True)


@pytest.mark.asyncio
async def test_redis_none_does_not_raise() -> None:
    """Calling record_request with redis=None is safe (e.g. during startup)."""
    await record_request(None, latency_ms=80.0, ok=True)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_hash_key_constant() -> None:
    """Verify hash key name matches contract documented in spec."""
    assert REDIS_HASH_KEY == "elevenlabs:stats"
    assert KEY_TOTAL == "total"
    assert KEY_OK == "ok"
    assert KEY_ERR == "err"
    assert KEY_LATENCY_SUM == "latency_ms_sum"
    assert KEY_LAST_SUCCESS_TS == "last_success_ts"
