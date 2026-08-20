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
    api_key: str = ""  # Bearer token for cloud OpenAI-compatible providers (e.g. xKiro); Ollama ignores it


@dataclass(frozen=True)
class SttConfig:
    engine: str = "faster_whisper"  # "faster_whisper" | "elevenlabs" | "sensevoice"
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "vi"
    end_of_utterance_silence_ms: int = 400



@dataclass(frozen=True)
class TtsConfig:
    engine: str
    voice: str
    sample_rate: int
    speed_factor: float
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    elevenlabs_stability: float = 0.71
    elevenlabs_similarity_boost: float = 0.75
    elevenlabs_style: float = 0.0
    elevenlabs_use_speaker_boost: bool = True
    elevenlabs_speed: float = 1.0
    xkiro_api_key: str = ""
    xkiro_tts_url: str = "https://api.xkiro.com/v1/audio/speech"
    xkiro_voice: str = "gentle-female-vietnamese"
    xkiro_model: str = "xkiro-voice"
    fallback_order: list[str] = None  # type: ignore[assignment]
    daily_char_quota: int = 0
    circuit_breaker_failures: int = 3
    circuit_breaker_reset_secs: int = 300

    def __post_init__(self) -> None:
        if self.fallback_order is None:
            object.__setattr__(self, "fallback_order", ["local", "edge-tts", "elevenlabs"])


@dataclass(frozen=True)
class ConversationConfig:
    enabled: bool = False
    ollama_model: str = "qwen2.5:3b"
    system_prompt: str = ""
    max_history_turns: int = 5
    temperature: float = 0.3
    sentiment_enabled: bool = False
    kb_grounding_enabled: bool = True
    sentence_split_min_chars: int = 30


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
    conversation: ConversationConfig = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.conversation is None:
            object.__setattr__(self, "conversation", ConversationConfig())


def _parse(raw: dict) -> SystemConfig:  # type: ignore[type-arg]
    ai_raw = raw.get("ai", {})
    stt_raw = raw.get("stt", {})
    tts_raw = raw.get("tts", {})
    notify_raw = raw.get("notify", {})
    vw_raw = raw.get("voiceWorker", {})
    conv_raw = raw.get("conversation", {})

    # Where a DB row exists but leaves a field unset, fall back to this pod's
    # env config (configmap/secret) rather than to a hardcoded localhost — an
    # empty `ai` row used to silently point every deployed pod at
    # localhost:11434, so LLM NLU 404'd on every call.
    _settings = Settings()

    return SystemConfig(
        ai=AiConfig(
            ollama_base_url=ai_raw.get("ollamaBaseUrl") or _settings.llm_base_url,
            ollama_model=ai_raw.get("ollamaModel") or _settings.llm_model,
            nlu_timeout_ms=int(ai_raw.get("nluTimeoutMs", 800)),
            response_timeout_ms=int(ai_raw.get("responseTimeoutMs", 2000)),
            fallback_to_substring=bool(ai_raw.get("fallbackToSubstring", True)),
            api_key=ai_raw.get("apiKey") or _settings.xkiro_api_key or _settings.llm_api_key,
        ),
        stt=SttConfig(
            engine=stt_raw.get("engine", "faster_whisper"),
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
            elevenlabs_voice_id=tts_raw.get("elevenlabsVoiceId") or "d5HVupAWCwe4e6GvMCAL",
            elevenlabs_model_id=tts_raw.get("elevenlabsModelId") or "eleven_v3",
            elevenlabs_stability=float(tts_raw.get("elevenlabsStability") or 0.71),
            elevenlabs_similarity_boost=float(tts_raw.get("elevenlabsSimilarityBoost") or 0.75),
            elevenlabs_style=float(tts_raw.get("elevenlabsStyleExaggeration") or 0.0),
            elevenlabs_use_speaker_boost=bool(tts_raw.get("elevenlabsUseSpeakerBoost", True)),
            elevenlabs_speed=float(tts_raw.get("elevenlabsSpeed") or 1.0),
            # The tts_settings table has no xKiro columns yet, so these come
            # from the pod's env (k8s secret `ai-voice-xkiro` / .env) unless a
            # future migration adds them — without the fallback, selecting
            # engine="xkiro" would build an engine with an empty API key.
            xkiro_api_key=tts_raw.get("xkiroApiKey") or _settings.xkiro_api_key,
            xkiro_tts_url=tts_raw.get("xkiroTtsUrl") or _settings.xkiro_tts_url,
            xkiro_voice=tts_raw.get("xkiroVoice") or _settings.xkiro_voice,
            xkiro_model=tts_raw.get("xkiroModel") or _settings.xkiro_model,
            fallback_order=tts_raw.get("engineFallbackOrder") or ["edge-tts", "elevenlabs"],
            daily_char_quota=int(tts_raw.get("elevenlabsDailyCharQuota") or 0),
            circuit_breaker_failures=int(tts_raw.get("circuitBreakerFailures") or 3),
            circuit_breaker_reset_secs=int(tts_raw.get("circuitBreakerResetSecs") or 300),
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
        conversation=ConversationConfig(
            enabled=bool(conv_raw.get("enabled", False)),
            ollama_model=conv_raw.get("ollamaModel", "qwen2.5:3b"),
            system_prompt=conv_raw.get("systemPrompt", ""),
            max_history_turns=int(conv_raw.get("maxHistoryTurns", 5)),
            temperature=float(conv_raw.get("temperature", 0.3)),
            sentiment_enabled=bool(conv_raw.get("sentimentEnabled", False)),
            kb_grounding_enabled=bool(conv_raw.get("kbGroundingEnabled", True)),
            sentence_split_min_chars=int(conv_raw.get("sentenceSplitMinChars", 30)),
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
            api_key=settings.xkiro_api_key,
        ),
        stt=SttConfig(
            engine=settings.stt_engine,
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
            elevenlabs_speed=settings.elevenlabs_speed,
            xkiro_api_key=settings.xkiro_api_key,
            xkiro_tts_url=settings.xkiro_tts_url,
            xkiro_voice=settings.xkiro_voice,
            xkiro_model=settings.xkiro_model,
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
        conversation=ConversationConfig(),
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
