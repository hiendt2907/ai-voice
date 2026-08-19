"""LLM Conversation Engine — streaming response generation via Ollama.

Uses KB answer as grounding context (not as a direct template).
The LLM rephrases / elaborates using its persona + conversation history.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from tts.params import EmotionState

logger = logging.getLogger(__name__)


class ConversationEngine:
    def __init__(
        self,
        ollama_base_url: str,
        model: str,
        system_prompt: str,
        temperature: float = 0.3,
        max_history_turns: int = 5,
    ) -> None:
        self._url = ollama_base_url.rstrip("/")
        self._model = model
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._max_history_turns = max_history_turns

    _BASE_SYSTEM = (
        "Bạn là Linh, nhân viên tổng đài của phòng khám DoctorCheck.\n"
        "\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. CHỈ sử dụng thông tin có trong [Thông tin tham khảo] được cung cấp.\n"
        "2. TUYỆT ĐỐI KHÔNG tự bịa thêm bất kỳ thông tin nào không có trong context: "
        "không tự đặt ra giờ khám, giá cả, tên bác sĩ, quy trình, hay bất kỳ chi tiết nào.\n"
        "3. Nếu [Thông tin tham khảo] KHÔNG có câu trả lời: "
        "chỉ nói đúng một câu 'Dạ em xin phép chuyển anh/chị tới nhân viên để hỗ trợ trực tiếp ạ.' "
        "rồi dừng lại — không giải thích thêm.\n"
        "4. Câu trả lời: ngắn gọn 1-2 câu, bắt đầu bằng 'Dạ', xưng 'em', gọi khách là 'anh/chị'.\n"
        "5. Không lặp lại câu hỏi của khách. Không dùng bullet, tiêu đề hay markdown.\n"
        "6. Giọng thân thiện, tự nhiên như nhân viên tổng đài y tế chuyên nghiệp.\n"
    )

    def _build_system(self, emotion: EmotionState) -> str:
        base = self._system_prompt or self._BASE_SYSTEM
        if emotion.label in ("frustrated", "angry"):
            base += "\nKhách đang không hài lòng. Hãy nhẹ nhàng, thông cảm hơn bình thường."
        elif emotion.label == "confused":
            base += "\nKhách chưa hiểu rõ. Hãy giải thích ngắn gọn, rõ ràng từng ý."
        return base

    async def stream_response(
        self,
        utterance: str,
        kb_context: str | None,
        history: list[tuple[str, str]],
        emotion: EmotionState,
    ) -> AsyncGenerator[str, None]:
        """Yield LLM tokens as they arrive."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._build_system(emotion)},
        ]

        # Recent conversation history (last N turns)
        turns = history[-self._max_history_turns :]
        for user_text, agent_text in turns:
            messages.append({"role": "user", "content": user_text})
            messages.append({"role": "assistant", "content": agent_text})

        # Current user utterance with KB grounding
        user_content = utterance
        if kb_context:
            user_content = f"[Thông tin tham khảo]: {kb_context}\n\n[Câu hỏi]: {utterance}"
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "temperature": self._temperature,
        }

        endpoint = f"{self._url}/chat/completions"

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            async with client.stream("POST", endpoint, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    logger.warning(
                        "ConversationEngine HTTP %d: %s", resp.status_code, body[:200]
                    )
                    return

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content") or ""
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
