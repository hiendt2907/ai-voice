"""Microsoft Teams Incoming Webhook notifier for unknown questions."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 3


class TeamsNotifier:
    """POST question to a Teams Incoming Webhook with an action button."""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send(self, question: str, session_id: str, callback_url: str) -> str:
        """Send question card to Teams. Returns the question as message_id."""
        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": "Câu hỏi cần giải đáp",
            "themeColor": "0078D7",
            "title": "Câu hỏi ngoài phạm vi từ khách hàng",
            "text": f"**Session:** `{session_id}`\n\n**Câu hỏi:** {question}",
            "potentialAction": [
                {
                    "@type": "OpenUri",
                    "name": "Đã có câu trả lời",
                    "targets": [{"os": "default", "uri": callback_url}],
                }
            ],
        }

        for attempt in range(_RETRY_ATTEMPTS):
            try:
                resp = await self._client.post(self._webhook_url, json=card)
                resp.raise_for_status()
                logger.info("Teams notified: session=%s", session_id)
                return session_id
            except Exception as exc:
                logger.warning("Teams notify attempt %d failed: %s", attempt + 1, exc)
                if attempt == _RETRY_ATTEMPTS - 1:
                    raise

        return session_id  # unreachable but satisfies type checker

    async def aclose(self) -> None:
        await self._client.aclose()
