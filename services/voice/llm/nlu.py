"""LLM-based NLU: intent classification + slot extraction + scope detection.

Uses Ollama with qwen2.5 for Vietnamese understanding. Falls back to
substring-based matcher (runtime.intent_matcher) on timeout or error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

from llm.client import LLMClient

logger = logging.getLogger(__name__)

_NLU_TIMEOUT_S = 0.8  # 800ms budget per plan

_SYSTEM_PROMPT = """\
Bạn là NLU engine tiếng Việt cho hệ thống tổng đài y tế.
Nhiệm vụ: Phân loại intent, trích xuất slot, và xác định câu hỏi ngoài phạm vi.

Trả về JSON (không có markdown):
{
  "intent": "tên_intent hoặc null",
  "slots": {"key": "value"},
  "confidence": 0.0-1.0,
  "is_out_of_scope": true/false
}

Câu ngoài phạm vi (is_out_of_scope=true): câu hỏi về giá, chẩn đoán bệnh, \
thông tin bác sĩ cụ thể, câu hỏi không liên quan đến đặt lịch.
"""


@dataclass(frozen=True)
class LLMMatchResult:
    intent: str | None
    slots: dict[str, str]
    confidence: float
    is_out_of_scope: bool


def _build_intent_list(intents_catalog: list[dict]) -> str:
    lines = []
    for item in intents_catalog:
        name = item.get("intent", "")
        examples = [e["text"] for e in item.get("examples", [])[:3]]
        lines.append(f"- {name}: {', '.join(examples)}")
    return "\n".join(lines) if lines else "(không có intent nào)"


def _parse_llm_response(raw: str) -> LLMMatchResult:
    """Parse JSON from LLM response, tolerating markdown fences."""
    cleaned = re.sub(r"```(?:json)?\n?", "", raw).strip()
    try:
        data = json.loads(cleaned)
        return LLMMatchResult(
            intent=data.get("intent") or None,
            slots={k: str(v) for k, v in data.get("slots", {}).items()},
            confidence=float(data.get("confidence", 0.0)),
            is_out_of_scope=bool(data.get("is_out_of_scope", False)),
        )
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("LLM NLU parse error: %s | raw=%r", exc, raw[:200])
        return LLMMatchResult(intent=None, slots={}, confidence=0.0, is_out_of_scope=False)


class LLMNLUClassifier:
    """Intent + slot + scope classifier using any OpenAI-compatible LLM."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    async def classify_intent(
        self,
        utterance: str,
        intents_catalog: list[dict],
        slots_so_far: dict[str, str] | None = None,
    ) -> LLMMatchResult:
        """Classify intent and extract slots with 800ms timeout.

        Returns LLMMatchResult with is_out_of_scope=True when utterance falls
        outside the script's knowledge domain.
        """
        intent_list = _build_intent_list(intents_catalog)
        slots_ctx = json.dumps(slots_so_far or {}, ensure_ascii=False)

        user_content = (
            f"Danh sách intent:\n{intent_list}\n\n"
            f"Slot đã thu thập: {slots_ctx}\n\n"
            f"Câu người dùng: \"{utterance}\""
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            raw = await asyncio.wait_for(
                self._client.chat(messages, temperature=0.0),
                timeout=_NLU_TIMEOUT_S,
            )
            return _parse_llm_response(raw)
        except TimeoutError:
            logger.warning("LLM NLU timeout after %.0fms — using fallback", _NLU_TIMEOUT_S * 1000)
            raise
        except Exception as exc:
            logger.warning("LLM NLU error: %s — using fallback", exc)
            raise
