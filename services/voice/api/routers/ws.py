"""CloudFone mock WebSocket endpoint.

Protocol:
  CloudFone → Voice: {"event": "start", ...} | {"event": "utterance", "text": "..."} | {"event": "hangup"}
  Voice → CloudFone: {"event": "beat", ...} | {"event": "handoff"} | {"event": "hangup"}
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from cloudfone.protocol import (
    HangupPayload,
    HandoffPayload,
    InboundEvent,
    StartMessage,
    UtteranceMessage,
)
from runtime.executor import create_session, process_turn
from runtime.session import SessionState
from tts.streamer import stream_step_beats

router = APIRouter(prefix="/ws", tags=["websocket"])

_STEP_INDEX_CACHE: dict[str, dict[str, dict]] = {}


def _index_steps(script: dict) -> dict[str, dict]:
    return {s["id"]: s for s in script.get("steps", [])}


async def _send_beats(
    ws: WebSocket,
    step: dict,
    slots: dict[str, str],
    no_match_count: int,
    turn: int,
    t_start: float,
) -> None:
    async for beat in stream_step_beats(step, slots, no_match_count, turn, t_start):
        await ws.send_json(beat.to_dict())


@router.websocket("/call")
async def call_ws(ws: WebSocket, script_id: str = "") -> None:
    """CloudFone mock WS. Pass script_id as query param for script lookup (future)."""
    await ws.accept()

    state: SessionState | None = None
    script: dict[str, Any] = {}
    steps: dict[str, dict] = {}
    turn = 0

    try:
        async for raw in ws.iter_json():
            event_name: str = raw.get("event", "")

            if event_name == InboundEvent.START:
                start = StartMessage.from_dict(raw)
                # In production, load script from Redis/API by campaign_id.
                # For mock: script must be provided inline in the start message.
                script = raw.get("script", {})
                steps = _index_steps(script)
                state = create_session(script)

                step = steps.get(state.current_step_id, {})
                t0 = time.perf_counter()
                await _send_beats(ws, step, {}, 0, turn, t0)

                if step.get("type") in ("speak", "hangup"):
                    await ws.send_json(HangupPayload(step_id=state.current_step_id).to_dict())
                    break
                if step.get("type") == "handoff":
                    await ws.send_json(HandoffPayload(step_id=state.current_step_id).to_dict())
                    break

            elif event_name == InboundEvent.UTTERANCE and state is not None:
                utt = UtteranceMessage.from_dict(raw)
                t0 = time.perf_counter()
                turn += 1

                result = process_turn(state, script, utt.text)
                state = result.state

                if result.is_handoff:
                    step = steps.get(result.state.current_step_id, {})
                    await _send_beats(ws, step, dict(state.slots), 0, turn, t0)
                    await ws.send_json(HandoffPayload(step_id=state.current_step_id).to_dict())
                    break

                if result.is_completed:
                    step = steps.get(result.state.current_step_id, {})
                    await _send_beats(ws, step, dict(state.slots), 0, turn, t0)
                    await ws.send_json(HangupPayload(step_id=state.current_step_id).to_dict())
                    break

                if result.next_step_id is not None:
                    step = steps.get(result.next_step_id, {})
                    no_match = 0
                else:
                    step = steps.get(state.current_step_id, {})
                    no_match = state.get_no_match_count(state.current_step_id)

                await _send_beats(ws, step, dict(state.slots), no_match, turn, t0)

            elif event_name == InboundEvent.HANGUP:
                break

    except WebSocketDisconnect:
        pass
