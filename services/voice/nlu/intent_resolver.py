"""Vector-based intent resolver with confidence gradient.

Replaces the regex-based IntentMatcher. Uses cosine similarity against NLU store
intent examples to classify utterances, with three confidence tiers:

  confident  (≥ CONFIDENT_THRESHOLD):  proceed with action
  clarify    (≥ CLARIFY_THRESHOLD):    ask for clarification
  handoff    (< CLARIFY_THRESHOLD):    expert handoff or generic fallback

Structured slot extraction (dates, phones, names) still uses regex via slot_extractor —
those are parsing problems, not semantic matching problems.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

CONFIDENT_THRESHOLD = 0.72
CLARIFY_THRESHOLD = 0.50

ConfidenceTier = Literal["confident", "clarify", "handoff"]


@dataclass(frozen=True)
class NluResult:
    intent: str | None
    slots: dict[str, str]
    confidence: float
    tier: ConfidenceTier
    top_matches: list[tuple[str, float]] = field(default_factory=list)


def resolve(
    utterance: str,
    query_embedding: list[float],
    campaign_id: str | None = None,
    expected_intents: list[str] | None = None,
) -> NluResult:
    """Resolve intent from utterance using vector search.

    Args:
        utterance: Raw STT output.
        query_embedding: Pre-computed embedding of utterance.
        campaign_id: Optional campaign scope for NLU store lookup.

    Returns:
        NluResult with intent, extracted slots, confidence score, and tier.
    """
    from nlu.store import search_intents  # noqa: PLC0415
    from nlu.slot_extractor import extract_slots  # noqa: PLC0415

    # Extract structured slots unconditionally (regex-based, fast)
    extracted_slots = extract_slots(utterance)

    # Context-guided shortcut: when the step only accepts specific intents,
    # resolve affirmative/negative signals directly without vector search.
    if expected_intents:
        guided = _resolve_with_context(utterance, extracted_slots, expected_intents)
        if guided is not None:
            return guided

    # Vector search for intent
    matches = search_intents(query_embedding, top_k=3, campaign_id=campaign_id)

    top_matches = [(m.intent, m.score) for m in matches]

    if not matches:
        # NLU store empty — fall back to heuristic context inference
        inferred = _infer_from_context(utterance.lower(), extracted_slots)
        tier: ConfidenceTier = "clarify" if inferred else "handoff"
        return NluResult(
            intent=inferred,
            slots=extracted_slots,
            confidence=0.40 if inferred else 0.0,
            tier=tier,
            top_matches=[],
        )

    best = matches[0]
    score = best.score

    # Merge preset slots from the matched example into extracted slots
    # Extracted slots take precedence (user said it explicitly)
    merged_slots = {**best.preset_slots, **extracted_slots}

    tier = _score_to_tier(score)

    if tier == "handoff":
        # Before giving up, try heuristic context inference
        inferred = _infer_from_context(utterance.lower(), extracted_slots)
        if inferred:
            return NluResult(
                intent=inferred,
                slots=extracted_slots,
                confidence=0.42,
                tier="clarify",
                top_matches=top_matches,
            )

    return NluResult(
        intent=best.intent if tier != "handoff" else None,
        slots=merged_slots if tier != "handoff" else extracted_slots,
        confidence=score,
        tier=tier,
        top_matches=top_matches,
    )


def _score_to_tier(score: float) -> ConfidenceTier:
    if score >= CONFIDENT_THRESHOLD:
        return "confident"
    if score >= CLARIFY_THRESHOLD:
        return "clarify"
    return "handoff"


# ── Heuristic context inference (last resort) ────────────────────────────────
import re  # noqa: E402

_BOOKING_MARKERS = re.compile(
    r"\b(muốn khám|cần khám|đặt khám|đặt lịch|book lịch|đặt hẹn|đăng ký khám|muốn đặt"
    r"|cho tôi đặt|xin đặt|muốn đăng ký|cho đặt lịch)\b",
    re.IGNORECASE,
)
_SYMPTOM_MARKERS = re.compile(
    r"\b(bị|ốm|đau|mệt|sốt|ho|ngứa|nổi mẩn|nổi|viêm|tê|chóng mặt|khó thở|khó chịu"
    r"|không khỏe|triệu chứng|hồi hộp|tức ngực|tiêu chảy|táo bón|buồn nôn|sụt cân|rụng tóc"
    r"|phù|ù tai|chảy mũi|nghẹt mũi|mờ mắt|đỏ mắt|co giật|tê liệt)\b",
    re.IGNORECASE,
)
_INQUIRY_MARKERS = re.compile(
    r"\b(giá|phí|chi phí|bao nhiêu|thông tin|hỏi|tư vấn|cần chuẩn bị|cần nhịn"
    r"|mất bao lâu|thủ tục|gồm những gì|có những gì|bảo hiểm|được không|như thế nào)\b",
    re.IGNORECASE,
)
# ── Context-guided intent resolution ────────────────────────────────────────

_AFFIRM_RE = re.compile(
    r"^\s*(đúng|được|ok|vâng|ừ|ừm|oke|okay|yes|có|đồng ý|chính xác|đúng rồi|đúng vậy|đúng ạ|đúng thôi|chính xác rồi)\b",
    re.IGNORECASE,
)
_NEGATE_RE = re.compile(
    r"^\s*(không|không ạ|chưa đúng|sai|sai rồi|không phải|nope|no|thay đổi|đổi|sửa)",
    re.IGNORECASE,
)


def _resolve_with_context(
    utterance: str,
    slots: dict[str, str],
    expected_intents: list[str],
) -> NluResult | None:
    """Return a context-guided result when expected_intents constrains resolution.

    Only resolves if:
    - The utterance clearly starts with an affirmative or negative signal, AND
    - The matching polarity intent (confirm/deny) is in expected_intents.

    Returns None to fall through to normal vector search.
    """
    if "confirm" in expected_intents and _AFFIRM_RE.match(utterance):
        return NluResult(
            intent="confirm",
            slots=slots,
            confidence=0.88,
            tier="confident",
            top_matches=[("confirm", 0.88)],
        )
    if "deny" in expected_intents and _NEGATE_RE.match(utterance):
        return NluResult(
            intent="deny",
            slots=slots,
            confidence=0.88,
            tier="confident",
            top_matches=[("deny", 0.88)],
        )
    return None


def _infer_from_context(utterance_lower: str, slots: dict[str, str]) -> str | None:
    if _BOOKING_MARKERS.search(utterance_lower):
        return "book_appointment"
    if _SYMPTOM_MARKERS.search(utterance_lower):
        return "symptom_described"
    if _INQUIRY_MARKERS.search(utterance_lower):
        return "service_inquiry"
    if "specialty" in slots:
        return "book_appointment"
    return None
