"""ElevenLabs API metrics — record request counts and latency in Redis.

Pattern: single HSET key ``elevenlabs:stats`` with fields:
  total           — total requests (TTS + STT combined)
  ok              — successful requests
  err             — failed requests
  latency_ms_sum  — cumulative latency of successful requests (ms)
  last_success_ts — epoch ms of most recent successful request

All operations are best-effort; Redis failures are logged and swallowed
so that TTS/STT callers are never broken by metrics instrumentation.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

REDIS_HASH_KEY = "elevenlabs:stats"

# Field names — exported so tests and the NestJS reader share the same contract.
KEY_TOTAL = "total"
KEY_OK = "ok"
KEY_ERR = "err"
KEY_LATENCY_SUM = "latency_ms_sum"
KEY_LAST_SUCCESS_TS = "last_success_ts"


async def record_request(
    redis: object | None,
    latency_ms: float | None,
    ok: bool,
) -> None:
    """Increment ElevenLabs request counters in Redis.

    Args:
        redis: An ``redis.asyncio.Redis`` instance (from ``app.state.redis``).
               Passing ``None`` is safe — all writes are skipped silently.
        latency_ms: Round-trip latency in milliseconds. Only recorded when ok=True.
        ok: Whether the request succeeded.
    """
    if redis is None:
        return

    try:
        await redis.hincrbyfloat(REDIS_HASH_KEY, KEY_TOTAL, 1)  # type: ignore[union-attr]
        if ok:
            await redis.hincrbyfloat(REDIS_HASH_KEY, KEY_OK, 1)  # type: ignore[union-attr]
            if latency_ms is not None:
                await redis.hincrbyfloat(REDIS_HASH_KEY, KEY_LATENCY_SUM, latency_ms)  # type: ignore[union-attr]
            ts = time.time() * 1000  # epoch ms
            await redis.hset(REDIS_HASH_KEY, mapping={KEY_LAST_SUCCESS_TS: ts})  # type: ignore[union-attr]
        else:
            await redis.hincrbyfloat(REDIS_HASH_KEY, KEY_ERR, 1)  # type: ignore[union-attr]
    except Exception:
        logger.debug("ElevenLabs metrics: Redis write failed (best-effort, ignoring)", exc_info=True)
