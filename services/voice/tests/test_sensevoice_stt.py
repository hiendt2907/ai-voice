"""Tests for SenseVoiceSTT — mocks funasr to avoid model download."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from stt.faster_whisper_stt import STTResult


# ---------------------------------------------------------------------------
# Helpers: build a minimal funasr stub so the module can be imported
# ---------------------------------------------------------------------------

def _make_funasr_stub(generate_return: list | None = None) -> ModuleType:
    stub = ModuleType("funasr")
    model_instance = MagicMock()
    model_instance.generate.return_value = generate_return or [{"text": ""}]
    stub.AutoModel = MagicMock(return_value=model_instance)
    return stub


@pytest.fixture(autouse=True)
def _patch_funasr(monkeypatch):
    stub = _make_funasr_stub()
    monkeypatch.setitem(sys.modules, "funasr", stub)
    # Remove cached sensevoice_stt module so each test gets fresh import
    sys.modules.pop("stt.sensevoice_stt", None)
    yield
    sys.modules.pop("stt.sensevoice_stt", None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_pcm_returns_empty_result():
    from stt.sensevoice_stt import SenseVoiceSTT
    stt = SenseVoiceSTT()
    result = stt.transcribe_pcm(b"")
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.is_final is True


def test_emotion_parsed_from_tag(monkeypatch):
    stub = _make_funasr_stub([{"text": "<|HAPPY|>Xin chào ạ"}])
    monkeypatch.setitem(sys.modules, "funasr", stub)
    sys.modules.pop("stt.sensevoice_stt", None)

    from stt.sensevoice_stt import SenseVoiceSTT
    stt = SenseVoiceSTT()
    pcm = (np.zeros(8000, dtype=np.int16)).tobytes()
    result = stt.transcribe_pcm(pcm)

    assert result.emotion == "happy"
    assert result.text == "Xin chào ạ"


def test_neutral_emotion_normalized(monkeypatch):
    stub = _make_funasr_stub([{"text": "<|NEUTRAL|>Vâng ạ"}])
    monkeypatch.setitem(sys.modules, "funasr", stub)
    sys.modules.pop("stt.sensevoice_stt", None)

    from stt.sensevoice_stt import SenseVoiceSTT
    stt = SenseVoiceSTT()
    pcm = (np.zeros(8000, dtype=np.int16)).tobytes()
    result = stt.transcribe_pcm(pcm)

    assert result.emotion == "neutral"
    assert result.text == "Vâng ạ"


def test_unknown_emotion_returns_none(monkeypatch):
    stub = _make_funasr_stub([{"text": "<|UNKNOWN|>text"}])
    monkeypatch.setitem(sys.modules, "funasr", stub)
    sys.modules.pop("stt.sensevoice_stt", None)

    from stt.sensevoice_stt import SenseVoiceSTT
    stt = SenseVoiceSTT()
    pcm = (np.zeros(8000, dtype=np.int16)).tobytes()
    result = stt.transcribe_pcm(pcm)

    assert result.emotion is None


def test_resampling_called_for_8khz(monkeypatch):
    stub = _make_funasr_stub([{"text": ""}])
    monkeypatch.setitem(sys.modules, "funasr", stub)
    sys.modules.pop("stt.sensevoice_stt", None)

    resample_calls: list = []

    def fake_resample_poly(samples, up, down):
        resample_calls.append((up, down))
        return samples

    with patch("scipy.signal.resample_poly", fake_resample_poly):
        from stt.sensevoice_stt import SenseVoiceSTT
        stt = SenseVoiceSTT()
        pcm = (np.zeros(8000, dtype=np.int16)).tobytes()
        stt.transcribe_pcm(pcm, sample_rate=8000)

    assert len(resample_calls) == 1
    up, down = resample_calls[0]
    assert up == 2  # 8000 * 2 = 16000
    assert down == 1


def test_funasr_not_installed_raises_import_error(monkeypatch):
    monkeypatch.delitem(sys.modules, "funasr", raising=False)
    sys.modules["funasr"] = None  # type: ignore[assignment]
    sys.modules.pop("stt.sensevoice_stt", None)

    with pytest.raises((ImportError, TypeError)):
        from stt.sensevoice_stt import SenseVoiceSTT  # noqa: F401
        SenseVoiceSTT()

    sys.modules.pop("funasr", None)
    sys.modules.pop("stt.sensevoice_stt", None)


def test_generate_error_returns_empty(monkeypatch):
    stub = _make_funasr_stub()
    stub.AutoModel.return_value.generate.side_effect = RuntimeError("model error")
    monkeypatch.setitem(sys.modules, "funasr", stub)
    sys.modules.pop("stt.sensevoice_stt", None)

    from stt.sensevoice_stt import SenseVoiceSTT
    stt = SenseVoiceSTT()
    pcm = (np.zeros(8000, dtype=np.int16)).tobytes()
    result = stt.transcribe_pcm(pcm)

    assert result.text == ""
    assert result.confidence == 0.0
