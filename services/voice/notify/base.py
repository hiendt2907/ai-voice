"""Chat notifier protocol for out-of-scope question routing."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ChatNotifier(Protocol):
    async def send(self, question: str, session_id: str, callback_url: str) -> str:
        """Send question to a chat platform. Returns message_id for tracking."""
        ...
