"""Tests for Q1–Q4 new modules: params, chain, conversation, session emotion."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm.sentence_splitter import SentenceSplitter
from runtime.session import SessionState
from tts.fillers import FillerSelector
from tts.params import EmotionState, TTSParams


# ── TTSParams & EmotionState ─────────────────────────────────────────────────


def test_emotion_state_defaults():
    e = EmotionState()
    assert e.label == "neutral"
    params = e.to_tts_params("elevenlabs")
    assert params.speaking_rate == 1.0
    assert params.stability == 0.50


def test_emotion_state_frustrated_elevenlabs():
    e = EmotionState("frustrated")
    p = e.to_tts_params("elevenlabs")
    assert p.speaking_rate == 0.88
    assert p.stability == 0.78
    assert p.style == 0.10


def test_emotion_state_happy_edge_tts():
    e = EmotionState("happy")
    p = e.to_tts_params("edge-tts")
    # edge-tts: only speaking_rate, rest default
    assert p.speaking_rate == 1.10
    assert p.stability == 0.50  # default, not happy's 0.40


def test_emotion_state_angry_full_params():
    e = EmotionState("angry")
    p = e.to_tts_params("elevenlabs")
    assert p.speaking_rate == 0.75
    assert p.stability == 0.90


def test_emotion_state_unknown_label():
    e = EmotionState("unknown_label")
    p = e.to_tts_params("elevenlabs")
    assert p.speaking_rate == 1.0  # falls back to neutral


def test_tts_params_frozen():
    p = TTSParams()
    with pytest.raises((AttributeError, TypeError)):
        p.speaking_rate = 2.0  # type: ignore[misc]


# ── SessionState emotion_history ────────────────────────────────────────────


def make_session() -> SessionState:
    return SessionState(session_id="s1", script_id="sc1", current_step_id="step1")


def test_session_with_emotion():
    s = make_session()
    s2 = s.with_emotion("frustrated")
    assert s2.emotion_history == ("frustrated",)
    assert s.emotion_history == ()  # original unchanged


def test_session_current_emotion_empty():
    s = make_session()
    assert s.current_emotion() == "neutral"


def test_session_current_emotion_majority():
    s = make_session()
    s = s.with_emotion("frustrated")
    s = s.with_emotion("frustrated")
    s = s.with_emotion("neutral")
    assert s.current_emotion() == "frustrated"  # majority in last 3


def test_session_emotion_history_trim():
    s = make_session()
    for _ in range(10):
        s = s.with_emotion("angry")
    # max_keep=5 by default
    assert len(s.emotion_history) == 5


# ── FillerSelector emotion-aware ─────────────────────────────────────────────


def test_filler_next_for_emotion_angry():
    f = FillerSelector()
    filler = f.next_for_emotion("angry")
    assert "xin lỗi" in filler or "thông cảm" in filler or "không hài lòng" in filler


def test_filler_next_for_emotion_confused():
    f = FillerSelector()
    filler = f.next_for_emotion("confused")
    # clarifying pool
    assert any(w in filler for w in ["xác nhận", "hỏi thêm", "ý bác"])


def test_filler_next_for_emotion_neutral():
    f = FillerSelector()
    filler = f.next_for_emotion("neutral")
    # thinking pool
    assert filler in ("Dạ,", "Vâng,", "À,", "Ừm,")


# ── SentenceSplitter new rules ────────────────────────────────────────────────


def test_splitter_min30_filters_short():
    s = SentenceSplitter(min_chars=30)
    assert s.feed("Ngắn. ") == []


def test_splitter_min30_emits_long():
    s = SentenceSplitter(min_chars=30)
    r = s.feed("Đây là một câu đủ dài để có thể yield ra ngoài. ")
    assert len(r) == 1
    assert "Đây là một câu" in r[0]


def test_splitter_force_split_no_word_cut():
    s = SentenceSplitter(min_chars=30)
    # 110 chars, no punctuation → force split at word boundary
    long_text = "từ " * 37  # ~111 chars
    results = s.feed(long_text)
    assert len(results) >= 1
    for r in results:
        # Should never end mid-word (no trailing partial word)
        assert not r.endswith("từ"[:-1]) if r else True


def test_splitter_comma_rule():
    s = SentenceSplitter(min_chars=30)
    # Buffer ends with comma + buffer >= 30 chars
    text = "Dạ, bác đợi em kiểm tra một chút,"
    results = s.feed(text)
    assert len(results) == 1
    assert "kiểm tra" in results[0]


# ── CircuitBreaker ───────────────────────────────────────────────────────────


def test_circuit_breaker_opens_after_threshold():
    from tts.chain import CircuitBreaker

    cb = CircuitBreaker(threshold=3, reset_secs=300)
    cb.record_failure("elevenlabs")
    assert not cb.is_open("elevenlabs")
    cb.record_failure("elevenlabs")
    assert not cb.is_open("elevenlabs")
    cb.record_failure("elevenlabs")
    assert cb.is_open("elevenlabs")


def test_circuit_breaker_success_resets():
    from tts.chain import CircuitBreaker

    cb = CircuitBreaker(threshold=2, reset_secs=300)
    cb.record_failure("edge-tts")
    cb.record_failure("edge-tts")
    assert cb.is_open("edge-tts")
    cb.record_success("edge-tts")
    assert not cb.is_open("edge-tts")


def test_circuit_breaker_status():
    from tts.chain import CircuitBreaker

    cb = CircuitBreaker(threshold=1, reset_secs=300)
    assert cb.status("new-engine") == "closed"
    cb.record_failure("new-engine")
    assert cb.status("new-engine") == "open"


# ── ConversationEngine ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversation_engine_streams_tokens():
    from llm.conversation import ConversationEngine

    engine = ConversationEngine(
        ollama_base_url="http://localhost:11434/v1",
        model="qwen2.5:3b",
        system_prompt="",
        temperature=0.3,
        max_history_turns=5,
    )

    emotion = EmotionState("neutral")

    mock_response_lines = [
        'data: {"choices": [{"delta": {"content": "Dạ"}}]}',
        'data: {"choices": [{"delta": {"content": ", em"}}]}',
        'data: {"choices": [{"delta": {"content": " xin chào"}}]}',
        "data: [DONE]",
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = AsyncMock(return_value=iter(mock_response_lines))

    async def mock_aiter_lines():
        for line in mock_response_lines:
            yield line

    mock_resp.aiter_lines = mock_aiter_lines

    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_ctx)

    mock_client_ctx = MagicMock()
    mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("llm.conversation.httpx.AsyncClient", return_value=mock_client_ctx):
        tokens = []
        async for token in engine.stream_response(
            utterance="Xin chào",
            kb_context=None,
            history=[],
            emotion=emotion,
        ):
            tokens.append(token)

    assert "".join(tokens) == "Dạ, em xin chào"


def test_conversation_engine_build_system_frustrated():
    from llm.conversation import ConversationEngine

    engine = ConversationEngine(
        ollama_base_url="http://localhost:11434/v1",
        model="test",
        system_prompt="Bạn là trợ lý.",
        temperature=0.3,
        max_history_turns=5,
    )
    system = engine._build_system(EmotionState("frustrated"))
    assert "không hài lòng" in system or "nhẹ nhàng" in system


def test_conversation_engine_build_system_confused():
    from llm.conversation import ConversationEngine

    engine = ConversationEngine(
        ollama_base_url="http://localhost:11434/v1",
        model="test",
        system_prompt="",
        temperature=0.3,
        max_history_turns=5,
    )
    system = engine._build_system(EmotionState("confused"))
    assert "chưa hiểu" in system or "rõ ràng" in system
