"""Tests for AiDrivenExecutor — Phase 2: vector RAG path replaces LLM generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from runtime.ai_executor import AiDrivenExecutor, AiTurnResult

_BASIC_BODY = {
    "type": "ai_driven",
    "version": "1.0.0",
    "greeting": "Dạ, Doctor Check xin nghe ạ",
    "persona": {
        "fillers": ["Dạ", "À"],
        "barge_in": True,
        "gender_detect": False,
    },
    "rag": {"enabled": False, "linkedKbTags": []},
    "escalation": {
        "telegram": False,
        "template": "❓ {question}\n📞 {session_id}",
        "waiting_message": "Dạ em đang kiểm tra",
    },
    "fallback_message": "Dạ để em kiểm tra thêm ạ",
}


@pytest.mark.asyncio
async def test_first_turn_returns_greeting():
    executor = AiDrivenExecutor(_BASIC_BODY)
    result = await executor.process_turn("Xin chào", "sess-001")

    assert isinstance(result, AiTurnResult)
    assert result.main_response == "Dạ, Doctor Check xin nghe ạ"
    assert not result.escalated
    assert result.filler in ["Dạ", "À"]


@pytest.mark.asyncio
async def test_second_turn_without_rag_uses_fallback():
    executor = AiDrivenExecutor(_BASIC_BODY)
    await executor.process_turn("Xin chào", "sess-001")  # first turn
    result = await executor.process_turn("Giá khám là bao nhiêu?", "sess-001")

    assert result.main_response == "Dạ để em kiểm tra thêm ạ"
    assert not result.escalated


@pytest.mark.asyncio
async def test_rag_answer_returned_when_store_has_match():
    """Phase 2: vector RAG store returns answer (no LLM generation)."""
    body = {**_BASIC_BODY, "rag": {"enabled": True, "linkedKbTags": []}}

    mock_search_result = MagicMock()
    mock_search_result.answer = "Phòng khám mở cửa 8h-17h các ngày trong tuần ạ"
    mock_search_result.score = 0.92
    mock_search_result.article.id = "art-1"

    executor = AiDrivenExecutor(body)
    await executor.process_turn("Xin chào", "sess-001")  # first turn

    with (
        patch("runtime.ai_executor.asyncio.get_running_loop") as mock_loop,
        patch("rag.store.search", return_value=mock_search_result),
        patch("rag.embedder.embed_query", return_value=[0.1, 0.2]),
    ):
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=[0.1, 0.2])
        result = await executor.process_turn("Phòng khám mở cửa mấy giờ?", "sess-002")

    assert "8h" in result.main_response
    assert not result.escalated


@pytest.mark.asyncio
async def test_telegram_escalation_triggered_when_rag_below_threshold():
    """Phase 2→3: no RAG match + Telegram enabled → escalation."""
    body = {
        **_BASIC_BODY,
        "rag": {"enabled": True, "linkedKbTags": []},
        "escalation": {
            "telegram": True,
            "template": "❓ {question}\n📞 {session_id}",
            "waiting_message": "Dạ em đã gửi lên đội bác sĩ ạ",
        },
    }
    mock_telegram = MagicMock()
    mock_telegram.send = AsyncMock(return_value="12345")

    executor = AiDrivenExecutor(body, telegram_notifier=mock_telegram)
    await executor.process_turn("Xin chào", "sess-001")  # first turn

    with (
        patch("runtime.ai_executor.asyncio.get_running_loop") as mock_loop,
        patch("rag.store.search", return_value=None),  # no match → escalate
        patch("rag.embedder.embed_query", return_value=[0.1, 0.2]),
    ):
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=[0.1, 0.2])
        result = await executor.process_turn("Bác sĩ Nguyễn có lịch không?", "sess-001")

    assert result.escalated
    assert "gửi" in result.main_response or "bác sĩ" in result.main_response.lower()
    mock_telegram.send.assert_called_once()


@pytest.mark.asyncio
async def test_filler_chosen_from_persona():
    body = {**_BASIC_BODY, "persona": {**_BASIC_BODY["persona"], "fillers": ["Vâng ạ"]}}
    executor = AiDrivenExecutor(body)
    await executor.process_turn("hello", "s")  # consume first turn
    result = await executor.process_turn("thông tin", "s")
    assert result.filler == "Vâng ạ"


@pytest.mark.asyncio
async def test_rag_disabled_no_store_call():
    """When rag.enabled=False, store is never queried."""
    body = {**_BASIC_BODY, "rag": {"enabled": False}}
    executor = AiDrivenExecutor(body)
    await executor.process_turn("Xin chào", "s")

    with patch("rag.store.search") as mock_search:
        result = await executor.process_turn("Câu hỏi gì đó", "s")

    mock_search.assert_not_called()
    assert result.main_response == _BASIC_BODY["fallback_message"]


@pytest.mark.asyncio
async def test_rag_search_error_falls_back_gracefully():
    """On RAG error (embed fails), returns fallback without crashing."""
    body = {**_BASIC_BODY, "rag": {"enabled": True, "linkedKbTags": []}}
    executor = AiDrivenExecutor(body)
    await executor.process_turn("Xin chào", "s")

    with (
        patch("runtime.ai_executor.asyncio.get_running_loop") as mock_loop,
    ):
        mock_loop.return_value.run_in_executor = AsyncMock(side_effect=RuntimeError("embed failed"))
        result = await executor.process_turn("câu hỏi", "s")

    assert result.main_response == _BASIC_BODY["fallback_message"]
    assert not result.escalated
