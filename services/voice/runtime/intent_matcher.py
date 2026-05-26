"""Example-based intent matcher for mock replay and testing.

In production this will be replaced by an LLM-based NLU call.
Matching strategy: case-insensitive substring check against intent examples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MatchResult:
    intent: str | None
    slots: dict[str, str]
    confidence: float  # 0.0–1.0


_SLOT_HINTS = re.compile(r"\b(\d{1,2})\s*tháng\b", re.IGNORECASE)


def match_intent(utterance: str, intents: list[dict]) -> MatchResult:
    """Match utterance against intent catalog using example-based heuristics."""
    utterance_lower = utterance.lower().strip()

    best: MatchResult = MatchResult(intent=None, slots={}, confidence=0.0)

    for intent_def in intents:
        intent_name: str = intent_def["intent"]
        examples: list[dict] = intent_def.get("examples", [])

        for example in examples:
            example_text = example["text"].lower()
            if example_text in utterance_lower or utterance_lower in example_text:
                slots: dict[str, str] = {}
                # Merge any example-level slot hints
                example_slots: dict[str, str] = example.get("slots", {})
                slots.update(example_slots)

                score = len(example_text) / max(len(utterance_lower), 1)
                if score > best.confidence:
                    best = MatchResult(intent=intent_name, slots=slots, confidence=score)

    # Light slot extraction independent of intent
    extracted = _extract_slots(utterance)
    merged_slots = {**extracted, **best.slots}

    return MatchResult(intent=best.intent, slots=merged_slots, confidence=best.confidence)


def _extract_slots(utterance: str) -> dict[str, str]:
    slots: dict[str, str] = {}

    # Date: "ngày 15 tháng 6" or "ngày 15"
    date_m = re.search(r"ngày\s+(\d{1,2})(?:\s+tháng\s+(\d{1,2}))?", utterance, re.IGNORECASE)
    if date_m:
        day = date_m.group(1)
        month = date_m.group(2)
        slots["date"] = f"ngày {day}" + (f" tháng {month}" if month else "")

    # Time of day
    if re.search(r"\bsáng\b", utterance, re.IGNORECASE):
        slots["time_of_day"] = "sáng"
    elif re.search(r"\bchiều\b", utterance, re.IGNORECASE):
        slots["time_of_day"] = "chiều"

    return slots
