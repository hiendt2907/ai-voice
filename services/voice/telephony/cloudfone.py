"""CloudFone adapter — identity passthrough.

ws.py's internal event shape *is* the CloudFone wire shape, so this adapter
exists only to satisfy the TelephonyAdapter interface uniformly; it changes
nothing about current behavior.
"""

from __future__ import annotations

from typing import Any


class CloudFoneAdapter:
    name = "cloudfone"

    def normalize_inbound(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        return raw

    def encode_outbound(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [payload]

    async def on_call_end(self, reason: str, session_id: str) -> None:
        return None
