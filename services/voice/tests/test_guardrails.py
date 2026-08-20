"""Tests for runtime.guardrails — the deterministic Lớp 1 blacklist gate
that must reject banned topics even without any LLM call."""

from __future__ import annotations

import pytest

from runtime.guardrails import is_blacklisted


@pytest.mark.parametrize(
    "utterance",
    [
        "bác sĩ chẩn đoán giúp em với",
        "em bị đau đầu 3 ngày, có phải viêm xoang không ạ",
        "bác sĩ kê đơn thuốc gì cho em",
        "em nên uống thuốc liều lượng bao nhiêu",
        "tình trạng của em tiên lượng thế nào",
        "bệnh này có nguy hiểm không bác sĩ",
        "cho em hỏi giá chính xác là bao nhiêu",
    ],
)
def test_blacklisted_topics_are_flagged(utterance: str) -> None:
    assert is_blacklisted(utterance) is True


@pytest.mark.parametrize(
    "utterance",
    [
        "chủ nhật phòng khám có mở cửa không",
        "em muốn đặt lịch khám nội khoa",
        "địa chỉ phòng khám ở đâu ạ",
        "cho em xin số điện thoại liên hệ",
    ],
)
def test_in_scope_topics_are_not_flagged(utterance: str) -> None:
    assert is_blacklisted(utterance) is False


def test_blacklist_ignores_case() -> None:
    assert is_blacklisted("BÁC SĨ CHẨN ĐOÁN GIÚP EM") is True
