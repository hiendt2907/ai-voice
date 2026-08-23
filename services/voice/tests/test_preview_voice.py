"""Test endpoint nghe thử giọng — POST /preview/voice."""

from __future__ import annotations

import base64
import dataclasses
import io
import wave

import pytest

from api.remote_config import TtsConfig
from api.routers.preview import (
    VoicePreviewRequest,
    _apply_overrides,
    _pcm_to_wav,
)


def _base_cfg() -> TtsConfig:
    return TtsConfig(
        engine="xkiro",
        voice="vi-VN-HoaiMyNeural",
        sample_rate=8000,
        speed_factor=1.0,
        elevenlabs_api_key="",
        elevenlabs_voice_id="original-el-voice",
        elevenlabs_model_id="eleven_turbo_v2_5",
        xkiro_voice="gentle-female-vietnamese",
        fallback_order=["xkiro", "edge-tts"],
    )


class TestPcmToWav:
    def test_wraps_pcm_in_playable_wav_header(self):
        """PCM thô không có header → trình duyệt không phát được, phải bọc RIFF."""
        pcm = b"\x00\x01" * 800  # 800 sample 16-bit

        wav = _pcm_to_wav(pcm)

        assert wav[:4] == b"RIFF"
        assert wav[8:12] == b"WAVE"
        with wave.open(io.BytesIO(wav), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 8000
            assert wf.readframes(wf.getnframes()) == pcm

    def test_base64_roundtrip_preserves_audio(self):
        pcm = bytes(range(256)) * 4
        wav = _pcm_to_wav(pcm)

        decoded = base64.b64decode(base64.b64encode(wav).decode("ascii"))

        assert decoded == wav


class TestApplyOverrides:
    def test_returns_new_config_without_mutating_shared_one(self):
        """TtsConfig dùng chung cả tiến trình — override phải tạo bản sao."""
        cfg = _base_cfg()

        result = _apply_overrides(
            cfg, VoicePreviewRequest(text="xin chào", engine="edge-tts")
        )

        assert result is not cfg
        assert cfg.engine == "xkiro", "cấu hình gốc bị sửa"
        assert result.engine == "edge-tts"

    def test_selected_engine_moved_to_front_of_fallback_order(self):
        """Không đẩy lên đầu thì chain có thể chọn engine khác → nghe nhầm giọng."""
        cfg = _base_cfg()

        result = _apply_overrides(
            cfg, VoicePreviewRequest(text="xin chào", engine="edge-tts")
        )

        assert result.fallback_order[0] == "edge-tts"
        assert "xkiro" in result.fallback_order

    def test_engine_not_in_order_is_still_placed_first(self):
        cfg = _base_cfg()

        result = _apply_overrides(
            cfg, VoicePreviewRequest(text="xin chào", engine="piper")
        )

        assert result.fallback_order[0] == "piper"

    @pytest.mark.parametrize(
        ("engine", "field", "untouched"),
        [
            ("elevenlabs", "elevenlabs_voice_id", "xkiro_voice"),
            ("xkiro", "xkiro_voice", "elevenlabs_voice_id"),
            ("edge-tts", "voice", "xkiro_voice"),
        ],
    )
    def test_voice_routed_to_engine_specific_field(self, engine, field, untouched):
        """Mỗi engine đọc tên giọng ở một trường khác nhau — đặt sai chỗ là im lặng dùng giọng cũ."""
        cfg = _base_cfg()

        result = _apply_overrides(
            cfg, VoicePreviewRequest(text="xin chào", engine=engine, voice="giọng-mới")
        )

        assert getattr(result, field) == "giọng-mới"
        assert getattr(result, untouched) == getattr(cfg, untouched)

    def test_voice_uses_current_engine_when_no_engine_override(self):
        """Không override engine thì phải route theo engine đang cấu hình (xkiro)."""
        cfg = _base_cfg()

        result = _apply_overrides(
            cfg, VoicePreviewRequest(text="xin chào", voice="giọng-mới")
        )

        assert result.xkiro_voice == "giọng-mới"
        assert result.elevenlabs_voice_id == cfg.elevenlabs_voice_id

    def test_elevenlabs_tuning_params_applied(self):
        cfg = _base_cfg()

        result = _apply_overrides(
            cfg,
            VoicePreviewRequest(
                text="xin chào",
                stability=0.9,
                similarity_boost=0.4,
                style=0.15,
                use_speaker_boost=False,
            ),
        )

        assert result.elevenlabs_stability == 0.9
        assert result.elevenlabs_similarity_boost == 0.4
        assert result.elevenlabs_style == 0.15
        assert result.elevenlabs_use_speaker_boost is False

    def test_zero_valued_params_are_applied_not_skipped(self):
        """0.0 là giá trị hợp lệ — dùng `if x:` thay vì `is not None` sẽ nuốt mất."""
        cfg = dataclasses.replace(_base_cfg(), elevenlabs_style=0.5)

        result = _apply_overrides(cfg, VoicePreviewRequest(text="xin chào", style=0.0))

        assert result.elevenlabs_style == 0.0

    def test_no_overrides_returns_config_unchanged(self):
        cfg = _base_cfg()

        result = _apply_overrides(cfg, VoicePreviewRequest(text="xin chào"))

        assert result is cfg


class TestRequestValidation:
    def test_empty_text_rejected(self):
        with pytest.raises(ValueError):
            VoicePreviewRequest(text="")

    def test_overlong_text_rejected(self):
        with pytest.raises(ValueError):
            VoicePreviewRequest(text="a" * 501)
