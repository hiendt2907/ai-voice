"""Stateful LLM-based intent resolver.

Unlike per-turn vector NLU, this resolver passes the full conversation
history to a local LLM (Ollama) so it understands call context holistically.
Each session's transcript (stored in SessionState) is the history.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from nlu.intent_resolver import CLARIFY_THRESHOLD, CONFIDENT_THRESHOLD, NluResult
from nlu.slot_extractor import extract_slots
from runtime.session import SessionState

logger = logging.getLogger(__name__)

# LLM_BASE_URL is what deploy/k8s's configmap actually sets (and what
# api/config.py's Settings.llm_base_url reads); OLLAMA_BASE_URL is kept first
# for backwards compatibility with existing local .env files. Reading only
# OLLAMA_BASE_URL meant every deployed pod silently fell back to localhost and
# every LLM NLU call 404'd.
_OLLAMA_BASE_URL = (
    os.getenv("OLLAMA_BASE_URL")
    or os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").removesuffix("/v1")
)
_OLLAMA_MODEL = os.getenv("LLM_NLU_MODEL", os.getenv("LLM_MODEL", "qwen2.5:1.5b"))
_TIMEOUT_S = float(os.getenv("LLM_NLU_TIMEOUT_S", "5"))
_LLM_API_KEY = os.getenv("XKIRO_API_KEY", "") or os.getenv("LLM_API_KEY", "")


async def _chat_json(messages: list[dict], *, max_tokens: int, temperature: float, timeout_s: float) -> str:
    """One JSON-mode completion over the OpenAI-compatible `/v1/chat/completions`
    endpoint. Ollama serves this alongside its native `/api/chat`, and cloud
    providers (xKiro) serve *only* this — so using it keeps both reachable
    from the same code path.
    """
    headers = {"Authorization": f"Bearer {_LLM_API_KEY}"} if _LLM_API_KEY else {}
    async with httpx.AsyncClient(timeout=timeout_s, headers=headers) as client:
        response = await client.post(
            f"{_OLLAMA_BASE_URL}/v1/chat/completions",
            json={
                "model": _OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
    data = response.json()
    return str(data["choices"][0]["message"]["content"])

_SYSTEM_TEMPLATE_CONSTRAINED = """\
Classify the LAST user message. Return JSON only.

Step: {current_step_id}
Collected: {slots}

MUST pick one of these intents (or null):
{expected_intents_detail}

Output: {{"intent":"name_or_null","slots":{{}},"confidence":0.0}}
"""

_SYSTEM_TEMPLATE = """\
Classify the LAST user message into one intent. Return JSON only.

Step: {current_step_id}
Collected: {slots}

Available intents:
{intents_list}

Output: {{"intent":"name_or_null","slots":{{}},"confidence":0.0}}
Rules: intent must be exact name from list, or null. Do NOT use step name.
"""


def _build_intents_list(script_intents: list[dict]) -> str:
    lines = []
    for intent in script_intents:
        name = intent.get("name") or intent.get("intent", "")  # script uses either field
        examples = intent.get("examples", [])[:2]
        example_texts = [e if isinstance(e, str) else e.get("text", "") for e in examples]
        examples_str = ", ".join(f'"{e}"' for e in example_texts if e)
        lines.append(f"- {name}: {examples_str}")
    return "\n".join(lines) if lines else "(không có)"


def _build_messages(
    utterance: str,
    state: SessionState,
    script_body: dict,
    expected_intents: list[str],
) -> list[dict]:
    script_intents: list[dict] = script_body.get("intents", [])

    _AUTO_SLOTS = {"today_date", "today_weekday", "today_full", "tomorrow_date", "tomorrow_full"}
    slots_str = ", ".join(
        f"{k}={v}" for k, v in state.slots.items() if k not in _AUTO_SLOTS
    ) or "none"

    if expected_intents:
        # Constrained: only show the step's expected intents → smaller model can focus
        intent_by_name = {
            (i.get("name") or i.get("intent", "")): i
            for i in script_intents
        }
        detail_lines = []
        for name in expected_intents:
            i = intent_by_name.get(name)
            if i:
                examples = i.get("examples", [])[:3]
                texts = [e if isinstance(e, str) else e.get("text", "") for e in examples]
                detail_lines.append(f'- {name}: {", ".join(repr(t) for t in texts if t)}')
            else:
                detail_lines.append(f"- {name}")
        system_content = _SYSTEM_TEMPLATE_CONSTRAINED.format(
            current_step_id=state.current_step_id,
            slots=slots_str,
            expected_intents_detail="\n".join(detail_lines),
        )
    else:
        system_content = _SYSTEM_TEMPLATE.format(
            current_step_id=state.current_step_id,
            slots=slots_str,
            intents_list=_build_intents_list(script_intents),
        )

    messages: list[dict] = [{"role": "system", "content": system_content}]

    if expected_intents:
        # Constrained mode: minimal context — last agent turn + current utterance
        # Full history confuses small models when intent is clear from single utterance
        last_agent = next(
            (e.text for e in reversed(state.transcript) if e.role == "agent"), None
        )
        if last_agent:
            messages.append({"role": "assistant", "content": last_agent})
    else:
        # Open-ended mode: use full conversation history for context
        for entry in state.transcript:
            if entry.role == "agent":
                messages.append({"role": "assistant", "content": entry.text})
            elif entry.role == "user":
                messages.append({"role": "user", "content": entry.text})

    messages.append({"role": "user", "content": utterance})
    return messages


async def resolve_with_llm(
    utterance: str,
    state: SessionState,
    script_body: dict,
    expected_intents: list[str],
) -> NluResult:
    """Resolve intent using full conversation context via local LLM."""
    # Regex slot extractor always runs first — reliable for dates/phones/names
    extracted_slots = extract_slots(utterance)

    messages = _build_messages(utterance, state, script_body, expected_intents)

    raw_content = await _chat_json(
        messages, max_tokens=150, temperature=0.1, timeout_s=_TIMEOUT_S
    )

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        logger.warning("LLM NLU non-JSON response: %.200s", raw_content)
        raise ValueError("non-JSON from LLM NLU")

    raw_intent = parsed.get("intent")
    confidence = float(parsed.get("confidence") or 0.5)
    # Only keep semantic slots from LLM — regex handles date/time/name/phone
    _SEMANTIC_SLOTS = {"specialty", "service_type"}
    raw_slots: dict = parsed.get("slots") or {}
    llm_slots: dict = {k: v for k, v in raw_slots.items() if k in _SEMANTIC_SLOTS and v}

    # Validate: intent must be a plain string from the valid intents list
    valid_names = {
        i.get("name") or i.get("intent", "")
        for i in script_body.get("intents", [])
    }
    if not isinstance(raw_intent, str) or raw_intent not in valid_names:
        intent = None  # hallucination: step_id, example utterance, or unknown value
    else:
        intent = raw_intent

    # Regex-extracted slots take precedence over LLM-extracted slots
    merged_slots = {**llm_slots, **extracted_slots}

    if confidence >= CONFIDENT_THRESHOLD:
        tier = "confident"
    elif confidence >= CLARIFY_THRESHOLD:
        tier = "clarify"
    else:
        tier = "handoff"

    logger.info(
        "LLM NLU: step=%s utterance=%.30r intent=%s conf=%.2f tier=%s",
        state.current_step_id, utterance, intent, confidence, tier,
    )

    return NluResult(
        intent=intent if tier != "handoff" else None,
        slots=merged_slots,
        confidence=confidence,
        tier=tier,
        top_matches=[(intent, confidence)] if intent else [],
    )


_SYSTEM_TEMPLATE_STT_CORRECT = """\
Bạn đang xem transcript một cuộc gọi tới phòng khám. Hệ thống vừa không trích \
xuất được thông tin sau từ câu khách VỪA NÓI (dòng "user" cuối cùng): {slot_desc}.

Có hai khả năng, dựa vào TOÀN BỘ hội thoại bên dưới để phân biệt:
1. STT nghe nhầm một từ tiếng Việt phổ thông thành từ gần âm — ví dụ "hôm nay" \
bị nghe thành "hãy nay".
2. Khách nói đúng, nhưng diễn đạt theo cách khác với từ khóa hệ thống nhận \
diện được.
{vocab_section}
Dựa vào TOÀN BỘ hội thoại để hiểu đúng ý khách, rồi VIẾT LẠI câu khách VỪA NÓI \
sao cho khớp với từ khóa/mẫu câu hệ thống hiểu được ở trên (nếu có liên quan) \
— giữ nguyên đúng nội dung khách đã nói, KHÔNG suy đoán hay thêm thông tin \
khách chưa từng nhắc tới ở bất kỳ đâu trong hội thoại. Chỉ sửa khi bạn tin \
chắc dựa trên ngữ cảnh đã có; nếu không đủ căn cứ, giữ nguyên nguyên văn.

Chỉ trả JSON, không giải thích: {{"corrected_text":"..."}}
"""

_SLOT_DESCRIPTIONS_VN = {
    "appointment_date": "ngày muốn khám",
    "time_of_day": "buổi trong ngày (sáng/chiều/tối)",
    "appointment_hour": "giờ muốn khám",
    "patient_name": "họ tên khách",
    "patient_phone": "số điện thoại khách",
    "specialty": "chuyên khoa muốn khám",
}

# Only date/time slots have a closed keyword vocabulary the regex extractor
# understands — must match runtime/../nlu/slot_extractor.py's actual patterns,
# not a paraphrase of them, or the model will "correct" into a form the regex
# still can't parse (see: qwen3.5-flash tested "hai hôm nữa" → left unchanged
# without this, and only produced "ngày mốt" once given this exact list).
_SLOT_VOCAB_HINTS = {
    "appointment_date": (
        'Bộ trích xuất chỉ hiểu ĐÚNG các từ khóa sau cho ngày: "hôm nay" (+0), '
        '"ngày mai" (+1), "ngày mốt" (+2), "ngày kia" (+3), "ngày kìa" (+4) — '
        'đây là 5 từ khác nhau, KHÔNG được coi bất kỳ 2 từ nào trong số này là '
        'đồng nghĩa. Ngoài ra còn "tuần sau", tên thứ trong tuần ("thứ Hai"..'
        '"Chủ Nhật"), ngày/tháng dạng số (vd "20/8", "ngày 20 tháng 8"), và '
        'cách đếm "hai/ba/bốn/năm/sáu/bảy hôm (hoặc ngày/bữa) nữa" (vd "ba '
        'hôm nữa" = +3 ngày = tương đương "ngày kia", "bốn hôm nữa" = +4 '
        'ngày = tương đương "ngày kìa" — LUÔN cộng đúng số ngày, không đoán '
        'áng chừng).'
    ),
    "time_of_day": 'Bộ trích xuất chỉ hiểu "sáng", "chiều", "tối".',
}


def _describe_slots(slot_names: list[str]) -> str:
    return ", ".join(_SLOT_DESCRIPTIONS_VN.get(s, s) for s in slot_names)


def _vocab_section(slot_names: list[str]) -> str:
    hints = [_SLOT_VOCAB_HINTS[s] for s in slot_names if s in _SLOT_VOCAB_HINTS]
    return "\n" + "\n".join(hints) + "\n" if hints else ""


async def correct_utterance_with_context(
    utterance: str, state: SessionState, missing_slots: list[str] | None = None
) -> str:
    """Best-effort re-phrasing of the caller's last utterance using the *full*
    conversation transcript — covers both STT mishearing AND phrasing the
    regex extractor doesn't recognize even when STT heard it correctly.

    Used only as a slot-recovery retry when a step's required slot came back
    empty from the regex extractor — never to answer the caller directly, so
    a bad guess here is inert: the corrected text is fed straight back into
    `extract_slots()` (the same trusted regex used everywhere else), and if
    nothing matches, the caller falls through to the normal reprompt/handoff
    path exactly as if this had never run. That is what keeps this safe to
    call with full history despite the "don't fabricate" guardrail elsewhere
    in the system — nothing generated here is ever spoken.
    """
    slot_desc = _describe_slots(missing_slots) if missing_slots else "thông tin còn thiếu"
    vocab_section = _vocab_section(missing_slots) if missing_slots else ""
    system_content = _SYSTEM_TEMPLATE_STT_CORRECT.format(
        slot_desc=slot_desc, vocab_section=vocab_section
    )
    messages: list[dict] = [{"role": "system", "content": system_content}]
    for entry in state.transcript:
        if entry.role == "agent":
            messages.append({"role": "assistant", "content": entry.text})
        elif entry.role == "user":
            messages.append({"role": "user", "content": entry.text})
    messages.append({"role": "user", "content": utterance})

    try:
        raw_content = await _chat_json(
            messages, max_tokens=100, temperature=0.1, timeout_s=_TIMEOUT_S
        )
        parsed = json.loads(raw_content)
        corrected = parsed.get("corrected_text")
        return corrected if isinstance(corrected, str) and corrected.strip() else utterance
    except Exception as exc:
        logger.info("STT context-correction unavailable, keeping original text: %s", exc)
        return utterance


async def warmup() -> None:
    """Pre-load the LLM model into memory to avoid cold-start latency on first call."""
    try:
        await _chat_json(
            [{"role": "user", "content": "ok"}],
            max_tokens=5, temperature=0.0, timeout_s=30.0,
        )
        logger.info("LLM NLU warmup done (model=%s)", _OLLAMA_MODEL)
    except Exception as exc:
        logger.debug("LLM NLU warmup skipped: %s", exc)
