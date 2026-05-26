from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    voice_port: int = 8000
    redis_url: str = "redis://localhost:6379"
    nestjs_webhook_url: str = "http://localhost:3001/api/v1/internal/call-events"
    doctorcheck_api_url: str = "https://www.doctorcheck.vn/api"
    stt_model: str = "small"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"

    # CloudFone ODS
    cloudfone_ws_url: str = ""
    cloudfone_service_name: str = ""
    cloudfone_auth_user: str = ""
    cloudfone_auth_key: str = ""
