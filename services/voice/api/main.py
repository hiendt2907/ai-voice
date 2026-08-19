import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .remote_config import RemoteConfig, SystemConfig, TtsConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s [%(name)s] %(message)s",
)

settings = Settings()
logger = logging.getLogger(__name__)


async def _build_redis(redis_url: str):  # type: ignore[return]
    """Create and connect an async Redis client. Returns None on failure."""
    try:
        from redis.asyncio import Redis  # noqa: PLC0415
        client = Redis.from_url(redis_url, decode_responses=True)
        await client.ping()
        logger.info("Redis connected: %s", redis_url)
        return client
    except Exception as exc:
        logger.warning("Redis not available (%s) — metrics will be skipped", exc)
        return None


def _build_tts(tts_cfg: TtsConfig, redis: object | None = None):  # type: ignore[return]
    """Build a TTS engine instance from remote/fallback config."""
    if tts_cfg.engine == "elevenlabs" and tts_cfg.elevenlabs_api_key:
        from tts.elevenlabs_tts import ElevenLabsTTS  # noqa: PLC0415
        logger.info(
            "TTS engine: ElevenLabs (voice=%s model=%s)",
            tts_cfg.elevenlabs_voice_id,
            tts_cfg.elevenlabs_model_id,
        )
        return ElevenLabsTTS(
            api_key=tts_cfg.elevenlabs_api_key,
            voice_id=tts_cfg.elevenlabs_voice_id,
            model_id=tts_cfg.elevenlabs_model_id,
            redis=redis,
            stability=tts_cfg.elevenlabs_stability,
            similarity_boost=tts_cfg.elevenlabs_similarity_boost,
            style=tts_cfg.elevenlabs_style,
            use_speaker_boost=tts_cfg.elevenlabs_use_speaker_boost,
        )
    if tts_cfg.engine == "edge-tts":
        from tts.edge_tts import EdgeTTS  # noqa: PLC0415
        voice = tts_cfg.voice or "vi-VN-HoaiMyNeural"
        logger.info("TTS engine: edge-tts (voice=%s)", voice)
        return EdgeTTS(voice=voice)
    if tts_cfg.engine == "remote":
        from tts.remote_tts import RemoteTTS  # noqa: PLC0415
        logger.info("TTS engine: remote inference server (%s)", settings.inference_server_url)
        return RemoteTTS(
            base_url=settings.inference_server_url,
            token=settings.inference_server_token,
        )
    if tts_cfg.engine == "piper":
        from tts.piper_tts import PiperTTS  # noqa: PLC0415
        logger.info("TTS engine: piper (local ONNX)")
        return PiperTTS()
    if tts_cfg.engine == "gwen-tts":
        from tts.synthesis import GwenTTS  # noqa: PLC0415
        logger.info("TTS engine: gwen-tts (model=%s)", settings.tts_model_id)
        return GwenTTS(
            model_id=settings.tts_model_id,
            ref_audio_path=settings.tts_ref_audio or None,
            device=settings.tts_device,
        )
    logger.info("TTS engine: disabled (beat-only mode)")
    return None


def _build_stt(sys_cfg: SystemConfig, redis: object | None = None):  # type: ignore[return]
    """Build STT engine from DB config (sys_cfg.stt.engine), fallback to env var via _fallback()."""
    engine = sys_cfg.stt.engine
    api_key = sys_cfg.tts.elevenlabs_api_key or settings.elevenlabs_api_key

    if engine == "remote":
        if settings.use_streaming_stt:
            from stt.streaming_remote_stt import StreamingRemoteSTT  # noqa: PLC0415
            logger.info(
                "STT engine: remote streaming (WS) inference server (%s)",
                settings.inference_server_url,
            )
            return StreamingRemoteSTT(
                base_url=settings.inference_server_url,
                token=settings.inference_server_token,
            )
        from stt.remote_stt import RemoteSTT  # noqa: PLC0415
        logger.info("STT engine: remote inference server (%s)", settings.inference_server_url)
        return RemoteSTT(
            base_url=settings.inference_server_url,
            token=settings.inference_server_token,
        )

    if engine == "sensevoice":
        from stt.sensevoice_stt import SenseVoiceSTT  # noqa: PLC0415
        device = sys_cfg.stt.device or settings.stt_device
        logger.info("STT engine: SenseVoice (device=%s)", device)
        return SenseVoiceSTT(device=device)

    if engine == "elevenlabs" and api_key:
        from stt.elevenlabs_stt import ElevenLabsSTT  # noqa: PLC0415
        logger.info("STT engine: ElevenLabs Scribe")
        return ElevenLabsSTT(api_key=api_key, redis=redis)

    # faster_whisper does not support MPS or float16 on CPU — normalise
    fw_device = sys_cfg.stt.device if sys_cfg.stt.device not in ("mps",) else "cpu"
    fw_compute = sys_cfg.stt.compute_type
    if fw_device == "cpu" and fw_compute in ("float16", "float16_fp32"):
        fw_compute = "int8"
    logger.info(
        "STT engine: faster-whisper (model=%s device=%s compute=%s)",
        sys_cfg.stt.model_size, fw_device, fw_compute,
    )
    from stt.faster_whisper_stt import FasterWhisperSTT  # noqa: PLC0415
    return FasterWhisperSTT(
        model_size=sys_cfg.stt.model_size,
        device=fw_device,
        compute_type=fw_compute,
    )


def _build_llm_client():  # type: ignore[return]
    """Build LLM client based on llm_provider setting."""
    if settings.llm_provider == "claude" and settings.anthropic_api_key:
        from llm.client import ClaudeNLUClient  # noqa: PLC0415
        logger.info("LLM provider: Claude (model=claude-haiku-4-5-20251001)")
        return ClaudeNLUClient(api_key=settings.anthropic_api_key, timeout_s=settings.llm_timeout_s)

    logger.info("LLM provider: OpenAI-compatible (model=%s url=%s)", settings.llm_model, settings.llm_base_url)
    from llm.client import LLMClient  # noqa: PLC0415
    return LLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout_s=settings.llm_timeout_s,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    remote_config = RemoteConfig(settings)
    system_config: SystemConfig = await remote_config.load()

    app.state.settings = settings
    app.state.remote_config = remote_config
    app.state.system_config = system_config

    # Redis singleton — built first so TTS/STT can reference it for metrics
    app.state.redis = await _build_redis(settings.redis_url)

    app.state.tts = _build_tts(system_config.tts, redis=app.state.redis)
    app.state.stt = _build_stt(system_config, redis=app.state.redis)
    app.state.llm_client = _build_llm_client()

    # Inject Redis into RAG store (must happen before reload)
    from rag import store as rag_store  # noqa: PLC0415
    rag_store.init(app.state.redis)

    # Load KB into RAG store (non-fatal — store starts empty if API unreachable)
    try:
        count = await rag_store.reload_from_api(settings.api_url)
        logger.info("RAG store loaded: %d articles", count)
    except Exception as exc:
        logger.warning("RAG store not loaded: %s", exc)

    # Load NLU documents into NLU store (intents, fillers, reprompts)
    try:
        from nlu.store import reload_from_api as nlu_reload  # noqa: PLC0415
        nlu_count = await nlu_reload(settings.api_url)
        logger.info("NLU store loaded: %d documents", nlu_count)
    except Exception as exc:
        logger.warning("NLU store not loaded (will use fallbacks): %s", exc)

    # Warm up Piper TTS singleton (eliminates 300ms first-call JIT penalty)
    try:
        # Probe: piper-tts is an optional extra (local-inference), absent in prod image.
        from piper import PiperVoice as _PiperVoice  # noqa: F401,PLC0415

        from tts.piper_tts import PiperTTS as _PiperTTS  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        _asyncio.create_task(_PiperTTS().warmup())
    except Exception as _piper_exc:
        logger.debug("Piper warmup skipped: %s", _piper_exc)

    # Warm up LLM NLU model (eliminates cold-start latency on first call)
    try:
        from nlu.llm_resolver import warmup as _llm_warmup  # noqa: PLC0415
        import asyncio as _asyncio2  # noqa: PLC0415
        _asyncio2.create_task(_llm_warmup())
    except Exception as _llm_exc:
        logger.debug("LLM NLU warmup skipped: %s", _llm_exc)

    yield

    # Shutdown: close Redis connection
    if app.state.redis is not None:
        await app.state.redis.aclose()


app = FastAPI(title="AI Voice Worker", version="0.0.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://doctorcheck.ai-agent.local"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routers import calls, callbacks, health, preview, ws  # noqa: E402
from .routers.rag import router as rag_router  # noqa: E402
from .routers.nlu import router as nlu_router  # noqa: E402
from fastapi import Request  # noqa: E402
from fastapi.routing import APIRouter  # noqa: E402

config_router = APIRouter(prefix="/config", tags=["config"])


@config_router.post("/reload")
async def reload_config(request: Request) -> dict:  # type: ignore[type-arg]
    """Re-fetch system config from NestJS API and re-init TTS/STT engines."""
    rc: RemoteConfig = request.app.state.remote_config
    new_cfg: SystemConfig = await rc.reload()
    request.app.state.system_config = new_cfg

    request.app.state.tts = _build_tts(new_cfg.tts, redis=request.app.state.redis)
    request.app.state.stt = _build_stt(new_cfg, redis=request.app.state.redis)

    return {
        "ok": True,
        "tts_engine": new_cfg.tts.engine,
        "tts_voice": new_cfg.tts.elevenlabs_voice_id,
        "stt_engine": new_cfg.stt.engine,
    }


app.include_router(health.router)
app.include_router(preview.router)
app.include_router(calls.router)
app.include_router(callbacks.router)
app.include_router(ws.router)
app.include_router(rag_router)
app.include_router(nlu_router)
app.include_router(config_router)
