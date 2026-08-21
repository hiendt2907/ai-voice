"""TTS Resilience Chain — CircuitBreaker + ElevenLabs quota tracker + fallback chain."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import redis.asyncio as aioredis

from api.remote_config import TtsConfig
from tts.params import TTSParams

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    pass


class CircuitBreaker:
    """Per-engine open/closed/half-open circuit breaker.

    State is in-memory per process. For multi-process deployments,
    use Redis-backed state (future improvement).
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

    def __init__(self, threshold: int = 3, reset_secs: int = 300) -> None:
        self._threshold = threshold
        self._reset_secs = reset_secs
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def record_failure(self, engine: str) -> None:
        self._failures[engine] = self._failures.get(engine, 0) + 1
        if self._failures[engine] >= self._threshold:
            self._opened_at[engine] = time.monotonic()
            logger.warning("CircuitBreaker OPEN for %s (failures=%d)", engine, self._failures[engine])

    def record_success(self, engine: str) -> None:
        self._failures[engine] = 0
        self._opened_at.pop(engine, None)

    def is_open(self, engine: str) -> bool:
        if engine not in self._opened_at:
            return False
        elapsed = time.monotonic() - self._opened_at[engine]
        if elapsed >= self._reset_secs:
            # Half-open: allow one retry
            return False
        return True

    def status(self, engine: str) -> str:
        if engine not in self._opened_at:
            return self.CLOSED
        elapsed = time.monotonic() - self._opened_at[engine]
        if elapsed >= self._reset_secs:
            return self.HALF_OPEN
        return self.OPEN


class ElevenLabsQuotaTracker:
    """Redis-backed daily character quota tracker for ElevenLabs."""

    def __init__(self, redis: "aioredis.Redis", daily_cap: int = 0) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._daily_cap = daily_cap

    def _key(self) -> str:
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        return f"quota:elevenlabs:{today}"

    async def count_chars(self, n: int) -> None:
        """Add n chars to today's usage. Raises QuotaExceededError if over cap."""
        if self._daily_cap <= 0:
            return
        key = self._key()
        try:
            new_count = await self._redis.incrby(key, n)
            await self._redis.expire(key, 86400 * 2)  # keep 2 days
            if new_count > self._daily_cap:
                logger.warning(
                    "ElevenLabs quota exceeded: %d / %d chars today", new_count, self._daily_cap
                )
                raise QuotaExceededError(f"Daily quota {self._daily_cap} exceeded ({new_count})")
        except QuotaExceededError:
            raise
        except Exception as exc:
            logger.warning("Quota tracker Redis error (non-fatal): %s", exc)

    async def status(self) -> dict[str, object]:
        key = self._key()
        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        try:
            raw = await self._redis.get(key)
            used = int(raw or 0)
        except Exception:
            used = 0
        cap = self._daily_cap
        return {
            "used": used,
            "cap": cap,
            "remaining": max(0, cap - used) if cap > 0 else -1,
            "date": today,
        }


async def _prepend(first: bytes | None, rest: AsyncGenerator[bytes, None]) -> AsyncGenerator[bytes, None]:
    """Re-attach a chunk already pulled out of `rest` back onto its stream."""
    if first is not None:
        yield first
    async for chunk in rest:
        yield chunk


class TTSChain:
    """Try engines in order; skip open circuits and exhausted quota."""

    def __init__(
        self,
        engines: list[object],
        engine_names: list[str],
        breaker: CircuitBreaker,
        quota: ElevenLabsQuotaTracker,
    ) -> None:
        self._engines = engines
        self._names = engine_names
        self._breaker = breaker
        self._quota = quota

    def primary_engine_name(self) -> str:
        for name in self._names:
            if not self._breaker.is_open(name):
                return name
        return self._names[0] if self._names else "unknown"

    def engine_status(self) -> dict[str, str]:
        return {name: self._breaker.status(name) for name in self._names}

    async def synthesize(self, text: str, params: TTSParams | None = None) -> bytes:
        last_exc: Exception | None = None
        for engine, name in zip(self._engines, self._names):
            if self._breaker.is_open(name):
                logger.debug("TTSChain: skip %s (circuit open)", name)
                continue
            try:
                if name == "elevenlabs":
                    await self._quota.count_chars(len(text))
                audio: bytes = await engine.synthesize(text, params)  # type: ignore[union-attr]
                self._breaker.record_success(name)
                return audio
            except QuotaExceededError as exc:
                logger.warning("TTSChain: ElevenLabs quota exhausted, trying next")
                last_exc = exc
            except Exception as exc:
                logger.warning("TTSChain: %s failed (%s), trying next", name, exc)
                self._breaker.record_failure(name)
                last_exc = exc
        raise RuntimeError(f"All TTS engines failed: {last_exc}") from last_exc

    async def stream_synthesize(
        self, text: str, params: TTSParams | None = None
    ) -> AsyncGenerator[bytes, None]:
        """Try each engine in order, falling back on failure.

        Calling `engine.stream_synthesize(...)` only constructs an async
        generator — for the HTTP-backed engines (xKiro, ElevenLabs, edge-tts)
        nothing actually happens over the network until it's iterated. A
        try/except around just the construction call therefore never sees
        the errors that matter (a 503, a dropped connection): the generator
        object comes back fine and the real failure only surfaces later, in
        the caller's `async for`, by which point this method has already
        returned and there is no more engine left to fall back to — a whole
        turn goes out silently instead of retrying on edge-tts. Priming the
        first chunk here, inside the try, is what makes the fallback real.
        """
        last_exc: Exception | None = None
        for engine, name in zip(self._engines, self._names):
            if self._breaker.is_open(name):
                continue
            try:
                if name == "elevenlabs":
                    await self._quota.count_chars(len(text))
                gen: AsyncGenerator[bytes, None] = await engine.stream_synthesize(text, params)  # type: ignore[union-attr]
                try:
                    first_chunk = await anext(gen)
                except StopAsyncIteration:
                    first_chunk = None
                self._breaker.record_success(name)
                return _prepend(first_chunk, gen)
            except QuotaExceededError as exc:
                last_exc = exc
                continue
            except Exception as exc:
                self._breaker.record_failure(name)
                last_exc = exc
                continue

        async def _empty() -> AsyncGenerator[bytes, None]:
            return
            yield b""  # pragma: no cover

        logger.error("TTSChain: all engines failed for stream_synthesize: %s", last_exc)
        return _empty()


def build_tts_chain(
    tts_cfg: TtsConfig,
    redis: "aioredis.Redis",  # type: ignore[type-arg]
) -> TTSChain:
    """Factory: build TTSChain from config. Called per-session."""
    from tts.edge_tts import EdgeTTS  # noqa: PLC0415
    from tts.elevenlabs_tts import ElevenLabsTTS  # noqa: PLC0415
    from tts.xkiro_tts import XkiroTTS  # noqa: PLC0415

    # If engine is explicitly chosen, ensure it appears first in the order.
    raw_order = tts_cfg.fallback_order or ["edge-tts", "elevenlabs"]
    primary = tts_cfg.engine  # e.g. "elevenlabs" / "edge-tts" / "local"
    if primary and primary in raw_order and raw_order[0] != primary:
        raw_order = [primary] + [n for n in raw_order if n != primary]
    elif primary and primary not in raw_order:
        raw_order = [primary] + raw_order
    fallback_order = raw_order
    engines: list[object] = []
    names: list[str] = []

    engine_map: dict[str, object] = {}

    if tts_cfg.elevenlabs_api_key:
        engine_map["elevenlabs"] = ElevenLabsTTS(
            api_key=tts_cfg.elevenlabs_api_key,
            voice_id=tts_cfg.elevenlabs_voice_id,
            model_id=tts_cfg.elevenlabs_model_id,
            stability=tts_cfg.elevenlabs_stability,
            similarity_boost=tts_cfg.elevenlabs_similarity_boost,
            style=tts_cfg.elevenlabs_style,
            use_speaker_boost=tts_cfg.elevenlabs_use_speaker_boost,
            speed=getattr(tts_cfg, "elevenlabs_speed", 1.0),
            redis=redis,
        )

    edge = EdgeTTS(voice=tts_cfg.voice)
    engine_map["edge-tts"] = edge

    if tts_cfg.xkiro_api_key:
        engine_map["xkiro"] = XkiroTTS(
            api_key=tts_cfg.xkiro_api_key,
            voice=tts_cfg.xkiro_voice,
            tts_url=tts_cfg.xkiro_tts_url,
            model=tts_cfg.xkiro_model,
        )

    # Remote inference server (heavy models run off-box) — needs httpx only.
    try:
        from api.config import Settings  # noqa: PLC0415
        from tts.remote_tts import RemoteTTS  # noqa: PLC0415

        _remote_settings = Settings()
        engine_map["remote"] = RemoteTTS(
            base_url=_remote_settings.inference_server_url,
            token=_remote_settings.inference_server_token,
        )
    except Exception as _remote_exc:  # pragma: no cover - defensive
        logger.warning("RemoteTTS unavailable: %s", _remote_exc)

    try:
        # Probe: piper-tts is an optional extra (local-inference), absent in prod image.
        from piper import PiperVoice  # noqa: F401,PLC0415

        from tts.piper_tts import PiperTTS  # noqa: PLC0415

        engine_map["local"] = PiperTTS()
        engine_map["piper"] = engine_map["local"]
    except Exception as _piper_exc:
        logger.debug("Piper TTS unavailable, local → edge-tts: %s", _piper_exc)
        engine_map["local"] = edge
        engine_map["piper"] = edge

    for name in fallback_order:
        eng = engine_map.get(name)
        if eng is not None:
            engines.append(eng)
            names.append(name)

    if not engines:
        engines.append(edge)
        names.append("edge-tts")

    breaker = CircuitBreaker(
        threshold=tts_cfg.circuit_breaker_failures,
        reset_secs=tts_cfg.circuit_breaker_reset_secs,
    )
    quota = ElevenLabsQuotaTracker(redis=redis, daily_cap=tts_cfg.daily_char_quota)

    logger.info("TTSChain built: %s", names)
    return TTSChain(engines=engines, engine_names=names, breaker=breaker, quota=quota)
