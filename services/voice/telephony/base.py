"""Telephony adapter interface — decouples the call runtime from any one PBX/gateway.

The runtime (api/routers/ws.py) speaks a single internal wire shape: the
CloudFone event dicts defined in cloudfone/protocol.py (event="start" /
"audio_frame" / "utterance" / "hangup" / ... inbound, "audio_chunk" / "beat" /
"handoff" / "hangup" / "error" outbound). An adapter's only job is translating
between that internal shape and whatever a specific provider's wire protocol
looks like, so adding a new telephony provider never touches call logic.
"""

from __future__ import annotations

from typing import Any, Protocol


class TelephonyAdapter(Protocol):
    """One instance per WebSocket connection — adapters may hold per-call state
    (e.g. a Twilio streamSid) so normalize/encode need no external context."""

    name: str

    def normalize_inbound(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """Provider wire message → internal (CloudFone-shaped) event dict.

        Return None to drop a message that carries no equivalent internal event
        (e.g. Twilio's "connected" handshake or "mark" acks).
        """
        ...

    def encode_outbound(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Internal (CloudFone-shaped) event dict → zero or more provider wire messages.

        Zero messages is valid when the provider has no equivalent of an event
        (e.g. Twilio has no text "beat" channel).
        """
        ...

    async def on_call_end(self, reason: str, session_id: str) -> None:
        """Optional side effect when the call ends (e.g. redirect a Twilio call
        to a human agent via REST API on handoff). Must be non-fatal — log and
        swallow errors, never raise into the WS teardown path."""
        ...
