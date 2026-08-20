"""Deterministic safety gate for the LLM reasoning tier (call/dialogue.py's
RAG-miss branch). Evaluated on the raw utterance BEFORE any LLM call, so it
can't be bypassed by prompt injection ("bỏ qua hướng dẫn trước, hãy...") —
a system-prompt-only rule can be talked out of by the caller, a regex can't.
"""

from __future__ import annotations

import re

_BANNED_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"chẩn đoán",
        r"(có phải|có phải là)\s+(bệnh|ung thư|viêm|nhiễm)",
        r"kê (đơn|thuốc)",
        r"(uống|dùng)\s+(thuốc|liều)",
        r"liều lượng",
        r"tiên lượng",
        r"có (nguy hiểm|nặng) không",
        r"giá (bao nhiêu|cụ thể|chính xác|thật)",
    )
]


def is_blacklisted(utterance: str) -> bool:
    """True when the utterance falls in a category the reasoning tier must
    never answer (diagnosis, prescription, prognosis, unconfirmed pricing) —
    these always route straight to human escalation instead."""
    return any(p.search(utterance) for p in _BANNED_PATTERNS)
