"""Telegram Bot notifier for unknown questions."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"
_RETRY_ATTEMPTS = 3


class TelegramNotifier:
    """Send question to a Telegram group via Bot API with inline reply button."""

    def __init__(self, bot_token: str, group_id: str) -> None:
        self._bot_token = bot_token
        self._group_id = group_id
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send(
        self, question: str, session_id: str, callback_url: str | None = None
    ) -> str:
        """Send message, kèm nút trả lời nếu có callback_url công khai.

        callback_url rỗng/None → gửi tin nhắn trơn. Telegram từ chối nút inline
        có URL không public ("Wrong HTTP URL") và trả 400 cho CẢ request, nên
        đính nút với URL nội bộ sẽ làm mất luôn thông báo — trong khi thông báo
        mới là thứ khiến bác sĩ biết mà gọi lại cho khách.
        """
        text = (
            f"🔔 *Câu hỏi cần giải đáp*\n\n"
            f"*Session:* `{session_id}`\n"
            f"*Câu hỏi:* {question}"
        )
        payload: dict = {
            "chat_id": self._group_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        if callback_url:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": "📝 Trả lời câu hỏi này", "url": callback_url}]
                ]
            }

        url = f"{_TELEGRAM_API}/bot{self._bot_token}/sendMessage"
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = await self._client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                message_id = str(data["result"]["message_id"])
                logger.info("Telegram notified: session=%s msg=%s", session_id, message_id)
                return message_id
            except Exception as exc:
                logger.warning("Telegram notify attempt %d failed: %s", attempt + 1, exc)
                if attempt == _RETRY_ATTEMPTS - 1:
                    raise

        return ""

    async def aclose(self) -> None:
        await self._client.aclose()
