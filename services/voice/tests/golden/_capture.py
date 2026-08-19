"""Golden-transcript capture/replay helper.

Connects to the real `/ws/call` endpoint (same as CloudFone would) and drives
a scripted conversation, recording only the *observable-over-the-wire*,
deterministic-ish fields: beat text, turn_meta (intent/slots/step transition),
and the terminal event (hangup/handoff + step_id).

Audio bytes are intentionally NOT recorded (non-deterministic engine/timing) —
only their presence/length, so a TTS engine swap doesn't break the golden
diff. This file is a test helper, not a test module itself (no `test_` name).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import websockets

from cloudfone.protocol import InboundEvent, OutboundEvent

DEFAULT_WS_URL = "ws://localhost:8000/ws/call"
_INITIAL_WAIT_S = 12.0
_QUIET_TIMEOUT_S = 2.0


@dataclass
class CapturedTurn:
    turn_index: int  # 0 = greeting, 1..N = after each caller utterance
    caller_utterance: str | None
    agent_text: str
    step_ids: list[str] = field(default_factory=list)
    audio_chunks: int = 0
    turn_meta: dict[str, Any] | None = None
    end_event: str | None = None  # "hangup" | "handoff" | None
    end_step_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "caller_utterance": self.caller_utterance,
            "agent_text": self.agent_text,
            "step_ids": self.step_ids,
            "audio_chunks": self.audio_chunks,
            "turn_meta": self.turn_meta,
            "end_event": self.end_event,
            "end_step_id": self.end_step_id,
        }


@dataclass
class CapturedCall:
    scenario: str
    script_id: str
    session_id: str
    turns: list[CapturedTurn]
    final_end_event: str | None
    final_end_step_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "script_id": self.script_id,
            "session_id": self.session_id,
            "turns": [t.to_dict() for t in self.turns],
            "final_end_event": self.final_end_event,
            "final_end_step_id": self.final_end_step_id,
        }


async def _collect_one_turn(
    ws: Any, turn_index: int, caller_utterance: str | None
) -> CapturedTurn:
    texts: list[str] = []
    step_ids: list[str] = []
    audio_chunks = 0
    turn_meta: dict[str, Any] | None = None
    end_event: str | None = None
    end_step_id = ""
    first_recv = True

    while True:
        timeout = _INITIAL_WAIT_S if first_recv else _QUIET_TIMEOUT_S
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            first_recv = False
        except asyncio.TimeoutError:
            break

        msg: dict[str, Any] = json.loads(raw)
        event = msg.get("event", "")

        if event == OutboundEvent.BEAT:
            if msg.get("text"):
                texts.append(msg["text"])
            if msg.get("step_id"):
                step_ids.append(msg["step_id"])
        elif event == OutboundEvent.AUDIO_CHUNK:
            audio_chunks += 1
        elif event == "turn_meta":
            turn_meta = {
                "intent": msg.get("intent"),
                "slots_new": msg.get("slots_new"),
                "step_from": msg.get("step_from"),
                "step_to": msg.get("step_to"),
                "nlu_tier": msg.get("nlu_tier"),
            }
        elif event == OutboundEvent.HANGUP:
            end_event = "hangup"
            end_step_id = msg.get("step_id", "")
            break
        elif event == OutboundEvent.HANDOFF:
            end_event = "handoff"
            end_step_id = msg.get("step_id", "")
            break

    return CapturedTurn(
        turn_index=turn_index,
        caller_utterance=caller_utterance,
        agent_text=" ".join(texts),
        step_ids=step_ids,
        audio_chunks=audio_chunks,
        turn_meta=turn_meta,
        end_event=end_event,
        end_step_id=end_step_id,
    )


async def run_scenario(
    scenario_name: str,
    script: dict[str, Any],
    caller_utterances: list[str],
    ws_url: str = DEFAULT_WS_URL,
    session_id: str | None = None,
) -> CapturedCall:
    """Drive one scripted call over the real WS endpoint (mock UTTERANCE mode,
    TTS disabled) and return the captured transcript."""
    sid = session_id or str(uuid.uuid4())
    turns: list[CapturedTurn] = []

    async with websockets.connect(ws_url) as ws:
        start_msg = {
            "event": InboundEvent.START,
            "session_id": sid,
            "campaign_id": script.get("campaign_id"),
            "script_version_id": script.get("id"),
            "direction": script.get("direction", "inbound"),
            "caller_number": "+84901234567",
            "caller_number_masked": "+849012****67",
            "script": script,
            "use_real_tts": False,  # deterministic/fast: beat-only, no engine call
        }
        await ws.send(json.dumps(start_msg))

        turn0 = await _collect_one_turn(ws, 0, None)
        turns.append(turn0)

        final_end_event = turn0.end_event
        final_end_step_id = turn0.end_step_id

        if not final_end_event:
            for i, utterance in enumerate(caller_utterances, start=1):
                utt_msg = {
                    "event": InboundEvent.UTTERANCE,
                    "text": utterance,
                    "confidence": 1.0,
                }
                await ws.send(json.dumps(utt_msg))
                t = await _collect_one_turn(ws, i, utterance)
                turns.append(t)
                if t.end_event:
                    final_end_event = t.end_event
                    final_end_step_id = t.end_step_id
                    break

            if not final_end_event:
                try:
                    await ws.send(json.dumps({"event": InboundEvent.HANGUP}))
                except websockets.exceptions.ConnectionClosed:
                    pass

    return CapturedCall(
        scenario=scenario_name,
        script_id=script.get("id", ""),
        session_id=sid,
        turns=turns,
        final_end_event=final_end_event,
        final_end_step_id=final_end_step_id,
    )
