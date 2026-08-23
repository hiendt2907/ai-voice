"""Preview endpoints — prosody timing (script CMS) và nghe thử giọng (voice profile)."""

from __future__ import annotations

import base64
import dataclasses
import io
import logging
import wave

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tts.prosody import beats_to_chunks, ProsodyChunk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/preview", tags=["preview"])

# Mọi engine TTS trong tts/ đều trả PCM 16-bit mono đã chuẩn hoá về 8kHz cho
# telephony (xkiro_tts._mp3_to_pcm8k, edge_tts._mp3_to_pcm8k, ...), nên header
# WAV dựng ở đây dùng chung một tần số — không lấy theo sampleRate của profile,
# vì đó là thông số đường truyền chứ không đổi được đầu ra của engine.
_PCM_SAMPLE_RATE = 8000
_PCM_SAMPLE_WIDTH = 2
_PCM_CHANNELS = 1


class PreviewRequest(BaseModel):
    beats: list[dict]


class PreviewResponse(BaseModel):
    chunks: list[ProsodyChunk]
    total_duration_ms: int


@router.post("", response_model=PreviewResponse)
async def preview_script(req: PreviewRequest):
    chunks = beats_to_chunks(req.beats)
    total_ms = sum(c.pause_after_ms for c in chunks)
    return PreviewResponse(chunks=chunks, total_duration_ms=total_ms)


class VoicePreviewRequest(BaseModel):
    """Tham số nghe thử một voice profile.

    Các trường override đều optional: bỏ trống thì dùng cấu hình TTS hiện hành
    của hệ thống, để nút "Nghe thử" vẫn phát được ngay cả với profile chỉ khai
    báo một phần.
    """

    text: str = Field(min_length=1, max_length=500)
    engine: str | None = None
    voice: str | None = None
    stability: float | None = None
    similarity_boost: float | None = None
    style: float | None = None
    use_speaker_boost: bool | None = None
    speaking_rate: float | None = None


class VoicePreviewResponse(BaseModel):
    audioBase64: str  # noqa: N815 — khớp tên trường Portal đang đọc
    engine: str
    sample_rate: int
    duration_ms: int


def _pcm_to_wav(pcm: bytes) -> bytes:
    """Bọc PCM thô thành file WAV.

    Bắt buộc: engine trả PCM KHÔNG có header, mà <audio> của trình duyệt chỉ
    phát được khi có header RIFF — trả thẳng PCM thì nút nghe thử im lặng.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(_PCM_CHANNELS)
        wf.setsampwidth(_PCM_SAMPLE_WIDTH)
        wf.setframerate(_PCM_SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


def _apply_overrides(tts_cfg, req: VoicePreviewRequest):
    """Trả về bản sao TtsConfig đã áp override của profile.

    TtsConfig là frozen dataclass — dùng dataclasses.replace() để tạo bản sao
    mới, không mutate cấu hình dùng chung của tiến trình.
    """
    changes: dict[str, object] = {}

    engine = req.engine or tts_cfg.engine
    if req.engine:
        changes["engine"] = req.engine
        # Đặt engine được chọn lên đầu chuỗi fallback, nếu không build_tts_chain
        # vẫn có thể ưu tiên engine khác và người dùng nghe nhầm giọng.
        order = list(tts_cfg.fallback_order or [])
        changes["fallback_order"] = [req.engine] + [n for n in order if n != req.engine]

    if req.voice:
        # Mỗi engine đọc tên giọng từ một trường khác nhau.
        if engine == "elevenlabs":
            changes["elevenlabs_voice_id"] = req.voice
        elif engine == "xkiro":
            changes["xkiro_voice"] = req.voice
        else:
            changes["voice"] = req.voice

    if req.stability is not None:
        changes["elevenlabs_stability"] = req.stability
    if req.similarity_boost is not None:
        changes["elevenlabs_similarity_boost"] = req.similarity_boost
    if req.style is not None:
        changes["elevenlabs_style"] = req.style
    if req.use_speaker_boost is not None:
        changes["elevenlabs_use_speaker_boost"] = req.use_speaker_boost

    return dataclasses.replace(tts_cfg, **changes) if changes else tts_cfg


@router.post("/voice", response_model=VoicePreviewResponse)
async def preview_voice(req: VoicePreviewRequest) -> VoicePreviewResponse:
    """Tổng hợp một câu ngắn bằng cấu hình của voice profile → WAV base64."""
    import redis.asyncio as aioredis  # noqa: PLC0415

    from api.config import Settings  # noqa: PLC0415
    from api.remote_config import RemoteConfig  # noqa: PLC0415
    from tts.chain import build_tts_chain  # noqa: PLC0415
    from tts.params import TTSParams  # noqa: PLC0415

    settings = Settings()
    try:
        cfg = await RemoteConfig(settings).load()
        redis = await aioredis.from_url(settings.redis_url, decode_responses=False)
        chain = build_tts_chain(_apply_overrides(cfg.tts, req), redis)
    except Exception as exc:
        logger.warning("Preview voice: không dựng được TTS chain: %s", exc)
        raise HTTPException(
            status_code=503, detail=f"Không dựng được TTS chain: {exc}"
        ) from exc

    params = TTSParams(speaking_rate=req.speaking_rate) if req.speaking_rate else None
    engine_used = chain.primary_engine_name()
    try:
        pcm = await chain.synthesize(req.text, params)
    except Exception as exc:
        logger.warning("Preview voice: tổng hợp thất bại: %s", exc)
        raise HTTPException(
            status_code=502, detail=f"Tổng hợp giọng thất bại: {exc}"
        ) from exc

    if not pcm:
        # Engine trả rỗng mà không ném lỗi — báo ra thay vì gửi WAV câm.
        raise HTTPException(
            status_code=502, detail="Engine TTS trả về audio rỗng"
        )

    wav = _pcm_to_wav(pcm)
    duration_ms = round(
        len(pcm) / (_PCM_SAMPLE_RATE * _PCM_SAMPLE_WIDTH * _PCM_CHANNELS) * 1000
    )
    return VoicePreviewResponse(
        audioBase64=base64.b64encode(wav).decode("ascii"),
        engine=engine_used,
        sample_rate=_PCM_SAMPLE_RATE,
        duration_ms=duration_ms,
    )
