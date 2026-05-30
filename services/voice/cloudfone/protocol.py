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
    AUDIO_FRAME = "audio_frame"         # real audio: base64 μ-law frame in "data"
    UTTERANCE = "utterance"             # mock / test: pre-transcribed text
    DTMF = "dtmf"
    HANGUP = "hangup"
    QUESTION_ANSWERED = "question_answered"  # answer injected from chat (Teams/Telegram)


class OutboundEvent(StrEnum):
    AUDIO_CHUNK = "audio_chunk"  # real audio: base64 PCM chunk in "data"
    BEAT = "beat"                # mock / test: prosody beat metadata
    HANDOFF = "handoff"          # transfer to human agent
    HANGUP = "hangup"            # end call
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


@dataclass(frozen=True)
class AudioChunkPayload:
    data: str   # base64-encoded PCM bytes
    turn: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"event": OutboundEvent.AUDIO_CHUNK, "data": self.data, "turn": self.turn}


@dataclass(frozen=True)
class QuestionAnsweredMessage:
    question_id: str
    answer: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "QuestionAnsweredMessage":
        return cls(
            question_id=d.get("question_id", ""),
            answer=d.get("answer", ""),
        )
