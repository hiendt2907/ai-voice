"""Example-based intent matcher for mock replay and testing.

In production this will be replaced by an LLM-based NLU call.
Matching strategy: case-insensitive substring check against intent examples.
Score is always in [0, 1]: exact=1.0, partial overlap = overlap/longer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nlu.slot_extractor import extract_slots as _extract_slots


@dataclass(frozen=True)
class MatchResult:
    intent: str | None
    slots: dict[str, str]
    confidence: float  # 0.0–1.0


# Explicit symptom/health-concern markers — caller describes what's wrong with their body
_SYMPTOM_MARKERS = re.compile(
    r"\b(bị|ốm|đau|mệt|sốt|ho|ngứa|nổi mẩn|nổi|viêm|tê|chóng mặt|khó thở|khó chịu"
    r"|không khỏe|triệu chứng|hồi hộp|tức ngực|tiêu chảy|táo bón|buồn nôn|sụt cân|rụng tóc"
    r"|phù|ù tai|chảy mũi|nghẹt mũi|mờ mắt|đỏ mắt|co giật|tê liệt)\b",
    re.IGNORECASE,
)

# Explicit booking-intent markers — caller says they want to book/register
_BOOKING_MARKERS = re.compile(
    r"\b(muốn khám|cần khám|đặt khám|đặt lịch|book lịch|đặt hẹn|đăng ký khám|muốn đặt"
    r"|cho tôi đặt|xin đặt|muốn đăng ký|cho đặt lịch)\b",
    re.IGNORECASE,
)

# Service/inquiry markers — caller is asking for information, not booking yet
_INQUIRY_MARKERS = re.compile(
    r"\b(giá|phí|chi phí|bao nhiêu|thông tin|hỏi|tư vấn|cần chuẩn bị|cần nhịn"
    r"|mất bao lâu|thủ tục|gồm những gì|có những gì|bảo hiểm|được không|như thế nào)\b",
    re.IGNORECASE,
)


def _score(utterance_lower: str, example_text: str) -> float:
    """Compute match score in [0, 1].

    Exact match = 1.0. Partial overlap = len(shorter) / len(longer).
    This keeps scores bounded and avoids false positives where a short
    affirmative like 'đúng' would outscore against a longer deny phrase
    like 'không đúng' under the old len(example)/len(utterance) formula.

    Leading-clause match ranks above any embedded-substring match. Real
    conversational Vietnamese leads with the direct reply to what the AI
    just asked, then elaborates/hedges after a comma. A dynamic LLM-caller
    test caught this: "ừ thì đặt đi, ... tôi hay đổi giờ lắm..." — the
    caller is CONFIRMING (leading "ừ"), but the old formula let the longer
    embedded "đổi giờ" (part of an unrelated aside deep in the sentence)
    outscore the short leading "ừ" purely because 7 chars > 2 chars, firing
    change_time and silently wiping the just-confirmed appointment slot.
    """
    if example_text == utterance_lower:
        return 1.0
    stripped = utterance_lower.lstrip()
    if stripped.startswith(example_text):
        after = stripped[len(example_text):]
        if not after or after[0] in " ,.!?;:":
            return 0.9 + len(example_text) / max(len(utterance_lower), 1) * 0.1
    if example_text in utterance_lower:
        return len(example_text) / max(len(utterance_lower), 1)
    if utterance_lower in example_text:
        return len(utterance_lower) / max(len(example_text), 1)
    return 0.0


def match_intent(utterance: str, intents: list[dict]) -> MatchResult:
    """Match utterance against intent catalog using example-based heuristics."""
    utterance_lower = utterance.lower().strip()

    best: MatchResult = MatchResult(intent=None, slots={}, confidence=0.0)

    for intent_def in intents:
        intent_name: str = intent_def["intent"]
        examples: list[dict] = intent_def.get("examples", [])

        for example in examples:
            example_text = example["text"].lower()
            score = _score(utterance_lower, example_text)
            if score > 0 and score > best.confidence:
                slots: dict[str, str] = dict(example.get("slots", {}))
                best = MatchResult(intent=intent_name, slots=slots, confidence=score)

    # Slot extraction independent of intent — single source of truth shared
    # with the LLM slot-recovery path (nlu/slot_extractor.py). This used to
    # be a second, hand-maintained copy of the same regex logic that had
    # drifted out of sync with bug fixes applied only to the other copy —
    # found when a dynamic LLM-caller test reproduced an already-fixed date
    # bug because the live turn pipeline was still calling the stale copy.
    extracted = _extract_slots(utterance)
    merged_slots = {**extracted, **best.slots}

    # When no intent matched (or low confidence) but caller described health symptoms,
    # infer intent from context so the FSM can route sensibly.
    if best.confidence < 0.3:
        inferred = _infer_intent_from_context(utterance_lower, merged_slots)
        if inferred is not None:
            return MatchResult(intent=inferred, slots=merged_slots, confidence=0.4)

    return MatchResult(intent=best.intent, slots=merged_slots, confidence=best.confidence)


def _infer_intent_from_context(utterance_lower: str, slots: dict[str, str]) -> str | None:
    """Infer intent when example matching fails.

    Priority order:
      1. Explicit booking phrase ("muốn khám", "đặt lịch")    → book_appointment
      2. Symptom markers ("bị đau", "ốm", "sốt")              → symptom_described
      3. Inquiry markers ("giá", "thông tin", "cần chuẩn bị") → service_inquiry
      4. Specialty slot extracted with no other signal         → book_appointment
    """
    if _BOOKING_MARKERS.search(utterance_lower):
        return "book_appointment"

    if _SYMPTOM_MARKERS.search(utterance_lower):
        return "symptom_described"

    if _INQUIRY_MARKERS.search(utterance_lower):
        return "service_inquiry"

    if "specialty" in slots:
        return "book_appointment"

    return None
