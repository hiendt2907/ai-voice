from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    voice_port: int = 8000
    redis_url: str = "redis://localhost:6379"
    nestjs_url: str = "http://localhost:3001"
    nestjs_webhook_url: str = "http://localhost:3001/api/v1/internal/call-events"
    service_api_key: str = ""
    doctorcheck_api_url: str = "https://www.doctorcheck.vn/api"

    # STT engine: "elevenlabs" | "faster_whisper"
    stt_engine: str = "elevenlabs"
    # ElevenLabs STT (shares key with TTS when using elevenlabs engine)
    # faster-whisper config (used when stt_engine == "faster_whisper")
    stt_model: str = "small"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"

    # LLM provider: "claude" | "ollama"
    llm_provider: str = "claude"   # "claude" uses Anthropic SDK directly
    anthropic_api_key: str = ""    # required when llm_provider == "claude"
    # OpenAI-compatible endpoint (used when llm_provider == "ollama")
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:latest"
    llm_api_key: str = "ollama"
    llm_timeout_s: float = 10.0

    # TTS engine: "elevenlabs" | "gwen"
    tts_engine: str = "elevenlabs"
    # ElevenLabs TTS
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "hpp4J3VqNfWAUOO0d1Us"
    elevenlabs_model_id: str = "eleven_turbo_v2_5"
    elevenlabs_stability: float = 0.6
    elevenlabs_similarity_boost: float = 0.75
    elevenlabs_style: float = 0.3
    elevenlabs_use_speaker_boost: bool = True
    # gwen-tts (fallback)
    tts_model_id: str = "g-group-ai-lab/gwen-tts-0.6B"
    tts_device: str = "cpu"
    tts_ref_audio: str = ""   # resolved at runtime from samples/ if empty

    # Notify (unknown questions → Teams/Telegram)
    notify_platform: str = "telegram"   # "teams" | "telegram"
    teams_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_group_id: str = ""
    voice_worker_base_url: str = "http://localhost:8000"
    question_timeout_seconds: int = 60

    # CloudFone ODS
    cloudfone_ws_url: str = ""
    cloudfone_service_name: str = ""
    cloudfone_auth_user: str = ""
    cloudfone_auth_key: str = ""

    # Feature flags
    use_real_ods: bool = False    # False → mock WS, True → real ODS
    use_llm_nlu: bool = False     # False → fallback to substring matcher
    use_real_tts: bool = False    # False → beat-only mode (no audio synthesis)

    # RAG — Knowledge Base
    api_url: str = "http://localhost:3001/api/v1"   # NestJS API base URL (includes /api/v1 prefix)
    internal_api_key: str = ""                       # x-internal-key header for service-to-service calls
    rag_confidence_default: float = 0.65             # calibrated for MiniLM-L12 dim=384 (max usable ~0.76)
