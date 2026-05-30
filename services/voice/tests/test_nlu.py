"""Tests for Sprint 2: LLM NLU client and sentence splitter."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm.nlu import LLMNLUClassifier, _parse_llm_response
from llm.sentence_splitter import SentenceSplitter


# ---------------------------------------------------------------------------
# _parse_llm_response tests (no network)
# ---------------------------------------------------------------------------


def test_parse_valid_json():
    raw = json.dumps({
        "intent": "book_appointment",
        "slots": {"date": "ngày 15 tháng 6"},
        "confidence": 0.95,
        "is_out_of_scope": False,
    })
    result = _parse_llm_response(raw)
    assert result.intent == "book_appointment"
    assert result.slots["date"] == "ngày 15 tháng 6"
    assert result.confidence == pytest.approx(0.95)
    assert result.is_out_of_scope is False


def test_parse_json_with_markdown_fence():
    raw = "```json\n{\"intent\": null, \"slots\": {}, \"confidence\": 0.0, \"is_out_of_scope\": true}\n```"
    result = _parse_llm_response(raw)
    assert result.intent is None
    assert result.is_out_of_scope is True


def test_parse_invalid_json_returns_default():
    result = _parse_llm_response("this is not json")
    assert result.intent is None
    assert result.slots == {}
    assert result.is_out_of_scope is False


def test_parse_out_of_scope():
    raw = json.dumps({
        "intent": None,
        "slots": {},
        "confidence": 0.1,
        "is_out_of_scope": True,
    })
    result = _parse_llm_response(raw)
    assert result.is_out_of_scope is True
    assert result.intent is None


# ---------------------------------------------------------------------------
# LLMNLUClassifier with mocked LLMClient
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.chat = AsyncMock(return_value=json.dumps({
        "intent": "book_appointment",
        "slots": {"date": "ngày 15 tháng 6"},
        "confidence": 0.9,
        "is_out_of_scope": False,
    }))
    return client


@pytest.fixture
def classifier(mock_client):
    return LLMNLUClassifier(mock_client)


INTENTS_CATALOG = [
    {"intent": "book_appointment", "examples": [{"text": "tôi muốn đặt lịch"}]},
    {"intent": "cancel", "examples": [{"text": "hủy lịch"}]},
]


async def test_classify_intent_success(classifier):
    result = await classifier.classify_intent("tôi muốn đặt lịch ngày 15", INTENTS_CATALOG)
    assert result.intent == "book_appointment"
    assert result.slots.get("date") == "ngày 15 tháng 6"
    assert result.confidence > 0.5
    assert result.is_out_of_scope is False


async def test_classify_intent_timeout_raises(mock_client):
    import asyncio
    mock_client.chat = AsyncMock(side_effect=asyncio.TimeoutError())
    classifier = LLMNLUClassifier(mock_client)
    with pytest.raises(asyncio.TimeoutError):
        await classifier.classify_intent("câu hỏi", INTENTS_CATALOG)


async def test_classify_out_of_scope(mock_client):
    mock_client.chat = AsyncMock(return_value=json.dumps({
        "intent": None,
        "slots": {},
        "confidence": 0.1,
        "is_out_of_scope": True,
    }))
    classifier = LLMNLUClassifier(mock_client)
    result = await classifier.classify_intent("giá khám bao nhiêu tiền?", INTENTS_CATALOG)
    assert result.is_out_of_scope is True
    assert result.intent is None


# ---------------------------------------------------------------------------
# SentenceSplitter tests
# ---------------------------------------------------------------------------


def test_splitter_basic_period():
    s = SentenceSplitter()
    assert s.feed("Dạ em xin nghe. ") == ["Dạ em xin nghe."]


def test_splitter_question_mark():
    s = SentenceSplitter()
    assert s.feed("Bạn cần hỗ trợ gì không? ") == ["Bạn cần hỗ trợ gì không?"]


def test_splitter_vietnamese_ending():
    s = SentenceSplitter()
    result = s.feed("Dạ vâng ạ. Bác cần em hỗ trợ thêm gì không ạ?")
    # First sentence emitted, second buffered
    assert len(result) >= 1
    assert any("Dạ vâng ạ." in r for r in result)


def test_splitter_accumulates_short_tokens():
    s = SentenceSplitter()
    assert s.feed("Xin") == []
    assert s.feed(" chào") == []
    assert s.feed(" bác.") == []
    result = s.feed(" ")
    assert len(result) == 1
    assert "Xin chào bác." in result[0]


def test_splitter_flush_remaining():
    s = SentenceSplitter()
    s.feed("Dạ em sẽ kiểm tra ngay")
    flushed = s.flush()
    assert len(flushed) == 1
    assert "Dạ em sẽ kiểm tra ngay" in flushed[0]


def test_splitter_flush_empty():
    s = SentenceSplitter()
    assert s.flush() == []


def test_splitter_multiple_sentences():
    s = SentenceSplitter()
    text = "Câu một xong rồi. Câu hai cũng xong. "
    result = s.feed(text)
    assert len(result) == 2
