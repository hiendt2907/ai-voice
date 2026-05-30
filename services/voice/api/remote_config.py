import json
import logging
from dataclasses import dataclass

import httpx
import redis.asyncio as aioredis

from .config import Settings

logger = logging.getLogger(__name__)

_CACHE_KEY = "config:system"
_CACHE_TTL = 300  # 5 minutes


@dataclass(frozen=True)
class AiConfig:
    ollama_base_url: str
    ollama_model: str
    nlu_timeout_ms: int
    response_timeout_ms: int
    fallback_to_substring: bool


@dataclass(frozen=True)
class SttConfig:
    model_size: str
    device: str
    compute_type: str
    language: str
    end_of_utterance_silence_ms: int


@dataclass(frozen=True)
class TtsConfig:
    engine: str
    voice: str
    sample_rate: int
    speed_factor: float
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    elevenlabs_stability: float = 0.6
    elevenlabs_similarity_boost: float = 0.75
    elevenlabs_style: float = 0.3
    elevenlabs_use_speaker_boost: bool = True


@dataclass(frozen=True)
class NotifyConfig:
    platform: str
    teams_webhook_url: str
    telegram_bot_token: str
    telegram_group_id: str
    question_timeout_seconds: int
    callback_delay_minutes: int


@dataclass(frozen=True)
class VoiceWorkerConfig:
    internal_url: str
    max_concurrent_sessions: int
    session_cache_ttl_seconds: int


@dataclass(frozen=True)
class SystemConfig:
    ai: AiConfig
    stt: SttConfig
    tts: TtsConfig
    notify: NotifyConfig
    voice_worker: VoiceWorkerConfig


def _parse(raw: dict) -> SystemConfig:  # type: ignore[type-arg]
    ai_raw = raw.get("ai", {})
    stt_raw = raw.get("stt", {})
    tts_raw = raw.get("tts", {})
    notify_raw = raw.get("notify", {})
    vw_raw = raw.get("voiceWorker", {})

    return SystemConfig(
        ai=AiConfig(
            ollama_base_url=ai_raw.get("ollamaBaseUrl", "http://localhost:11434/v1"),
            ollama_model=ai_raw.get("ollamaModel", "qwen2.5:latest"),
            nlu_timeout_ms=int(ai_raw.get("nluTimeoutMs", 800)),
            response_timeout_ms=int(ai_raw.get("responseTimeoutMs", 2000)),
            fallback_to_substring=bool(ai_raw.get("fallbackToSubstring", True)),
        ),
        stt=SttConfig(
            model_size=stt_raw.get("modelSize", "small"),
            device=stt_raw.get("device", "cpu"),
            compute_type=stt_raw.get("computeType", "int8"),
            language=stt_raw.get("language", "vi"),
            end_of_utterance_silence_ms=int(stt_raw.get("endOfUtteranceSilenceMs", 400)),
        ),
        tts=TtsConfig(
            engine=tts_raw.get("engine", "edge-tts"),
            voice=tts_raw.get("voice", "vi-VN-HoaiMyNeural"),
            sample_rate=int(tts_raw.get("sampleRate", 8000)),
            speed_factor=float(tts_raw.get("speedFactor", 1.0)),
            elevenlabs_api_key=tts_raw.get("elevenlabsApiKey") or "",
            elevenlabs_voice_id=tts_raw.get("elevenlabsVoiceId") or "hpp4J3VqNfWAUOO0d1Us",
            elevenlabs_model_id=tts_raw.get("elevenlabsModelId") or "eleven_turbo_v2_5",
            elevenlabs_stability=float(tts_raw.get("elevenlabsStability") or 0.6),
            elevenlabs_similarity_boost=float(tts_raw.get("elevenlabsSimilarityBoost") or 0.75),
            elevenlabs_style=float(tts_raw.get("elevenlabsStyleExaggeration") or 0.3),
            elevenlabs_use_speaker_boost=bool(tts_raw.get("elevenlabsUseSpeakerBoost", True)),
        ),
        notify=NotifyConfig(
            platform=notify_raw.get("platform", "telegram"),
            teams_webhook_url=notify_raw.get("teamsWebhookUrl", ""),
            telegram_bot_token=notify_raw.get("telegramBotToken", ""),
            telegram_group_id=notify_raw.get("telegramGroupId", ""),
            question_timeout_seconds=int(notify_raw.get("questionTimeoutSeconds", 300)),
            callback_delay_minutes=int(notify_raw.get("callbackDelayMinutes", 10)),
        ),
        voice_worker=VoiceWorkerConfig(
            internal_url=vw_raw.get("internalUrl", "http://localhost:8000"),
            max_concurrent_sessions=int(vw_raw.get("maxConcurrentSessions", 10)),
            session_cache_ttl_seconds=int(vw_raw.get("sessionCacheTtlSeconds", 3600)),
        ),
    )


def _fallback(settings: Settings) -> SystemConfig:
    """Build SystemConfig from env vars when NestJS API is unreachable."""
    return SystemConfig(
        ai=AiConfig(
            ollama_base_url=settings.llm_base_url,
            ollama_model=settings.llm_model,
            nlu_timeout_ms=800,
            response_timeout_ms=2000,
            fallback_to_substring=True,
        ),
        stt=SttConfig(
            model_size=settings.stt_model,
            device=settings.stt_device,
            compute_type=settings.stt_compute_type,
            language="vi",
            end_of_utterance_silence_ms=400,
        ),
        tts=TtsConfig(
            engine=settings.tts_engine,
            voice="reference",
            sample_rate=8000,
            speed_factor=1.0,
            elevenlabs_api_key=settings.elevenlabs_api_key,
            elevenlabs_voice_id=settings.elevenlabs_voice_id,
            elevenlabs_model_id=settings.elevenlabs_model_id,
            elevenlabs_stability=settings.elevenlabs_stability,
            elevenlabs_similarity_boost=settings.elevenlabs_similarity_boost,
            elevenlabs_style=settings.elevenlabs_style,
            elevenlabs_use_speaker_boost=settings.elevenlabs_use_speaker_boost,
        ),
        notify=NotifyConfig(
            platform=settings.notify_platform,
            teams_webhook_url=settings.teams_webhook_url,
            telegram_bot_token=settings.telegram_bot_token,
            telegram_group_id=settings.telegram_group_id,
            question_timeout_seconds=settings.question_timeout_seconds,
            callback_delay_minutes=10,
        ),
        voice_worker=VoiceWorkerConfig(
            internal_url=settings.voice_worker_base_url,
            max_concurrent_sessions=10,
            session_cache_ttl_seconds=3600,
        ),
    )


class RemoteConfig:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._redis: aioredis.Redis | None = None  # type: ignore[type-arg]

    async def _get_redis(self) -> "aioredis.Redis":  # type: ignore[type-arg]
        if self._redis is None:
            self._redis = await aioredis.from_url(self._settings.redis_url, decode_responses=True)
        return self._redis

    async def load(self) -> SystemConfig:
        try:
            r = await self._get_redis()
            cached = await r.get(_CACHE_KEY)
            if cached:
                return _parse(json.loads(cached))
        except Exception as e:
            logger.warning("Redis cache miss: %s", e)

        return await self._fetch_from_api()

    async def _fetch_from_api(self) -> SystemConfig:
        url = f"{self._settings.nestjs_url}/api/v1/internal/system-settings"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                res.raise_for_status()
                raw: dict = res.json()  # type: ignore[type-arg]

            config = _parse(raw)
            await self._write_cache(raw)
            logger.info(
                "System config loaded: stt.modelSize=%s, tts.engine=%s, ai.model=%s",
                config.stt.model_size,
                config.tts.engine,
                config.ai.ollama_model,
            )
            return config
        except Exception as e:
            logger.warning("NestJS unreachable (%s), falling back to env vars", e)
            return _fallback(self._settings)

    async def _write_cache(self, raw: dict) -> None:  # type: ignore[type-arg]
        try:
            r = await self._get_redis()
            await r.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(raw))
        except Exception as e:
            logger.warning("Failed to write config cache: %s", e)

    async def reload(self) -> SystemConfig:
        """Force reload from NestJS API, bypass cache."""
        try:
            r = await self._get_redis()
            await r.delete(_CACHE_KEY)
        except Exception:
            pass
        return await self._fetch_from_api()
