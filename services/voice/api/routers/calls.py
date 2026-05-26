"""Mock call replay endpoint for Sprint 3 testing."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from runtime.executor import TurnResult, create_session, process_turn

router = APIRouter(prefix="/calls", tags=["calls"])


class ReplayRequest(BaseModel):
    script: dict
    utterances: list[str | None]  # None = silence (no-match)
    max_turns: int = 20


class ReplayTurn(BaseModel):
    turn: int
    step_id: str
    step_type: str
    agent_text: str
    utterance: str | None
    matched_intent: str | None
    extracted_slots: dict[str, str]
    next_step_id: str | None
    is_handoff: bool
    is_completed: bool


class ReplayResponse(BaseModel):
    session_id: str
    final_status: str
    turns: list[ReplayTurn]
    final_slots: dict[str, str]


@router.post("/replay", response_model=ReplayResponse)
async def replay_call(req: ReplayRequest) -> ReplayResponse:
    state = create_session(req.script)
    steps_index = {s["id"]: s for s in req.script.get("steps", [])}
    turns: list[ReplayTurn] = []
    utterance_iter = iter(req.utterances)

    for turn_num in range(req.max_turns):
        step = steps_index.get(state.current_step_id)
        step_type = step.get("type", "speak") if step else "unknown"

        # Only consume an utterance for speak_listen steps
        utterance: str | None = None
        if step_type == "speak_listen":
            utterance = next(utterance_iter, None)

        result: TurnResult = process_turn(state, req.script, utterance)
        state = result.state

        turns.append(
            ReplayTurn(
                turn=turn_num + 1,
                step_id=result.state.current_step_id
                if result.next_step_id is None
                else turns[-1].step_id
                if turns
                else state.current_step_id,
                step_type=step_type,
                agent_text=result.agent_text,
                utterance=utterance,
                matched_intent=result.intent,
                extracted_slots=result.slots,
                next_step_id=result.next_step_id,
                is_handoff=result.is_handoff,
                is_completed=result.is_completed,
            )
        )

        if result.is_handoff or result.is_completed:
            break

        if result.next_step_id is None:
            # Still in reprompt cycle — continue same step
            continue

    return ReplayResponse(
        session_id=state.session_id,
        final_status=state.status,
        turns=turns,
        final_slots=dict(state.slots),
    )
