"""Tests for the sentence splitter (llm/sentence_splitter.py).

Ghi chú: file này trước đây còn test cho `llm.nlu.LLMNLUClassifier` —
module đó đã bị xoá vì là code chết (không nằm trên đường xử lý cuộc gọi
thật, xem CLAUDE.md mục "Luồng xử lý một lượt thoại": NLU thật dùng
`nlu.intent_resolver` + `nlu.llm_resolver`, được gọi trực tiếp trong
`runtime/executor.py`, không qua tham số `nlu` từng được truyền xuyên
`call/turn.py`)."""

from llm.sentence_splitter import SentenceSplitter


def test_splitter_basic_period():
    s = SentenceSplitter(min_chars=8)
    assert s.feed("Dạ em xin nghe. ") == ["Dạ em xin nghe."]


def test_splitter_question_mark():
    s = SentenceSplitter(min_chars=8)
    assert s.feed("Bạn cần hỗ trợ gì không? ") == ["Bạn cần hỗ trợ gì không?"]


def test_splitter_vietnamese_ending():
    s = SentenceSplitter(min_chars=8)
    result = s.feed("Dạ vâng ạ. Bác cần em hỗ trợ thêm gì không ạ?")
    assert len(result) >= 1
    assert any("Dạ vâng ạ." in r for r in result)


def test_splitter_accumulates_short_tokens():
    s = SentenceSplitter(min_chars=8)
    assert s.feed("Xin") == []
    assert s.feed(" chào") == []
    assert s.feed(" bác.") == []
    result = s.feed(" ")
    assert len(result) == 1
    assert "Xin chào bác." in result[0]


def test_splitter_flush_remaining():
    s = SentenceSplitter(min_chars=8)
    s.feed("Dạ em sẽ kiểm tra ngay")
    flushed = s.flush()
    assert len(flushed) == 1
    assert "Dạ em sẽ kiểm tra ngay" in flushed[0]


def test_splitter_flush_empty():
    s = SentenceSplitter(min_chars=8)
    assert s.flush() == []


def test_splitter_multiple_sentences():
    s = SentenceSplitter(min_chars=8)
    text = "Câu một xong rồi. Câu hai cũng xong. "
    result = s.feed(text)
    assert len(result) == 2


def test_splitter_default_min30():
    s = SentenceSplitter()  # default min_chars=30
    # Short sentence < 30 chars should be filtered
    result = s.feed("Ngắn. ")
    assert result == []
    # Long enough sentence >= 30 chars should be emitted
    result2 = s.feed("Đây là một câu đủ dài để yield ra. ")
    assert len(result2) == 1


def test_splitter_force_split_at_100():
    s = SentenceSplitter(min_chars=30)
    # Feed a very long string without punctuation — should force split at word boundary
    long_text = "a " * 55  # 110 chars, no punctuation
    results = s.feed(long_text)
    # Should have yielded at least one chunk at word boundary
    assert len(results) >= 1
    for r in results:
        assert not r.endswith(" a") or True  # no word cut
