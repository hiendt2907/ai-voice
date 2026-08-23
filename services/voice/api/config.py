from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    voice_port: int = 8000
    redis_url: str = "redis://localhost:6379"
    nestjs_url: str = "http://localhost:3001"
    nestjs_webhook_url: str = "http://localhost:3001/api/v1/internal/call-events"
    service_api_key: str = ""
    doctorcheck_api_url: str = "https://www.doctorcheck.vn/api"

    # Remote inference server (Macbook via Tailscale) — hosts Piper TTS + Whisper STT
    inference_server_url: str = "http://100.93.3.96:8100"
    # Shared service token sent as `Authorization: Bearer <token>` to the
    # inference server (D4 — Tailscale ACLs alone are not authentication).
    inference_server_token: str = ""

    # STT engine: "elevenlabs" | "faster_whisper" | "sensevoice" | "remote"
    stt_engine: str = "elevenlabs"
    # Phase 2 (D2/D5): when stt_engine == "remote", use the persistent WS
    # streaming client (StreamingRemoteSTT) instead of the HTTP one-shot
    # client (RemoteSTT). Default OFF — this must be opted into manually per
    # the Phase 2 task 1 scope; RemoteSTT/AudioPipeline remains the
    # production path until this has been validated.
    use_streaming_stt: bool = False
    # Phase 2 (D538/D989): swap the bare RMS-energy VAD for neural Silero
    # VAD (stt/silero_vad.py, onnxruntime-only — no torch dependency).
    # Default OFF pending the same canary rollout as use_streaming_stt.
    use_silero_vad: bool = False
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
    elevenlabs_voice_id: str = "d5HVupAWCwe4e6GvMCAL"
    elevenlabs_model_id: str = "eleven_v3"
    elevenlabs_stability: float = 0.71
    elevenlabs_similarity_boost: float = 0.75
    elevenlabs_style: float = 0.0
    elevenlabs_use_speaker_boost: bool = True
    elevenlabs_speed: float = 1.0
    # gwen-tts (fallback)
    tts_model_id: str = "g-group-ai-lab/gwen-tts-0.6B"
    tts_device: str = "cpu"
    tts_ref_audio: str = ""   # resolved at runtime from samples/ if empty
    # xKiro TTS (cloud, evaluation — see tts/xkiro_tts.py)
    xkiro_api_key: str = ""
    xkiro_tts_url: str = "https://api.xkiro.com/v1/audio/speech"
    xkiro_voice: str = "gentle-female-vietnamese"
    xkiro_model: str = "xkiro-voice"

    # Notify (unknown questions → Teams/Telegram)
    notify_platform: str = "telegram"   # "teams" | "telegram"
    teams_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_group_id: str = ""
    voice_worker_base_url: str = "http://localhost:8000"
    # Base URL công khai để dựng link trả lời gửi kèm thông báo Telegram.
    # PHẢI tách khỏi voice_worker_base_url: cái đó là địa chỉ nội bộ trong
    # cluster (http://voice:8000), Telegram từ chối thẳng URL như vậy trong
    # nút inline ("Wrong HTTP URL") khiến TOÀN BỘ thông báo thất bại, không
    # chỉ mất mỗi cái nút. Để trống thì gửi tin nhắn không kèm nút.
    public_callback_base_url: str = ""
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
    # Lower floor used only to decide whether an article is relevant enough to
    # hand to the LLM reasoning tier as grounding context (call/dialogue.py) —
    # below rag_confidence_default (not a confirmed direct answer) but above
    # this floor (not pure noise). Below this: no context, skip straight to
    # escalation instead of letting the LLM reason ungrounded.
    rag_context_floor: float = 0.45
    semantic_cache_ttl_s: int = 86400               # text cache TTL (seconds), default 24h
