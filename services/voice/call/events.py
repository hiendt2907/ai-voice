"""Internal call-event vocabulary + per-call context.

The internal protocol is the CloudFone-shaped event dict already defined in
`cloudfone/protocol.py` — `telephony/` adapters translate provider wire
messages to/from this shape (see `telephony/base.py`). Nothing here
redefines that wire shape; this module just re-exports it as the single
import point for `call/` collaborators, plus adds `CallContext`: the
mutable per-connection metadata that used to be a pile of `nonlocal`s in
`ws.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cloudfone.protocol import (
    AudioChunkPayload,
    BeatPayload,
    FlushPayload,
    HandoffPayload,
    HangupPayload,
    InboundEvent,
    OutboundEvent,
    QuestionAnsweredMessage,
    StartMessage,
    UtteranceMessage,
)

__all__ = [
    "AudioChunkPayload",
    "BeatPayload",
    "FlushPayload",
    "HandoffPayload",
    "HangupPayload",
    "InboundEvent",
    "OutboundEvent",
    "QuestionAnsweredMessage",
    "StartMessage",
    "UtteranceMessage",
    "CallContext",
]


@dataclass
class CallContext:
    """Per-connection call metadata, set once on START and read throughout
    the call's lifetime. Deliberately mutable (unlike `SessionState`, which
    is the immutable FSM state) — this is transport/session bookkeeping, not
    dialogue state.
    """

    session_id: str = ""
    campaign_id: str | None = None
    script_version_id: str | None = None
    caller_number: str | None = None
    caller_direction: str = "inbound"
    interception_mode: str = "full"  # shadow | medium | full
    interception_domains: list[str] = field(default_factory=list)

    script: dict[str, Any] = field(default_factory=dict)
    steps: dict[str, dict] = field(default_factory=dict)

    started_at: float = 0.0

    # Phase 2/4 call-metrics accumulators (persisted on hangup via
    # api/routers/ws.py -> _post_call_events equivalent).
    last_rag_score: float | None = None
    barge_in_count: int = 0

    # Glassbox: one decision record per caller turn. Emitted live over the
    # call WebSocket, exported as OTel spans, and persisted into
    # call_turns.metadata on hangup — see obs/turn_trace.py.
    trace_id: str = ""
    turn_traces: list[Any] = field(default_factory=list)
    # Engine names are recorded per turn so a trace shows which engine
    # actually served it — TTSChain falls back between engines mid-call.
    stt_engine_name: str = ""
    tts_engine_name: str = ""

    def script_exec_mode(self) -> str:
        """Explicit field takes priority, then infer from legacy `type`."""
        explicit = self.script.get("execution_mode")
        if explicit:
            return str(explicit)
        if self.script.get("type") == "ai_driven":
            return "rag_assisted"
        return "fsm"
