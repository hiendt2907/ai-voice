"""CloudFone ODS WebSocket protocol types (mock implementation).

Actual ODS schema is pending — this mirrors the expected protocol
based on the CloudFone integration spec. Will be updated when ODS
documentation is provided.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InboundEvent(StrEnum):
    START = "start"
    UTTERANCE = "utterance"  # mock STT result (real: audio frames)
    DTMF = "dtmf"
    HANGUP = "hangup"


class OutboundEvent(StrEnum):
    BEAT = "beat"          # one prosody beat to synthesise
    HANDOFF = "handoff"    # transfer to human agent
    HANGUP = "hangup"      # end call
    ERROR = "error"


@dataclass(frozen=True)
class StartMessage:
    session_id: str
    campaign_id: str | None
    script_version_id: str | None
    direction: str
    caller_number: str | None
    caller_number_masked: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StartMessage":
        return cls(
            session_id=d.get("session_id", ""),
            campaign_id=d.get("campaign_id"),
            script_version_id=d.get("script_version_id"),
            direction=d.get("direction", "inbound"),
            caller_number=d.get("caller_number"),
            caller_number_masked=d.get("caller_number_masked"),
        )


@dataclass(frozen=True)
class UtteranceMessage:
    text: str
    confidence: float = 1.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UtteranceMessage":
        return cls(
            text=d.get("text", ""),
            confidence=float(d.get("confidence", 1.0)),
        )


@dataclass(frozen=True)
class BeatPayload:
    text: str
    pause_ms: int
    turn: int
    step_id: str
    ttfa_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "event": OutboundEvent.BEAT,
            "text": self.text,
            "pause_ms": self.pause_ms,
            "turn": self.turn,
            "step_id": self.step_id,
        }
        if self.ttfa_ms is not None:
            d["ttfa_ms"] = round(self.ttfa_ms, 1)
        return d


@dataclass(frozen=True)
class HandoffPayload:
    reason: str = "agent_request"
    step_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"event": OutboundEvent.HANDOFF, "reason": self.reason, "step_id": self.step_id}


@dataclass(frozen=True)
class HangupPayload:
    step_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"event": OutboundEvent.HANGUP, "step_id": self.step_id}
