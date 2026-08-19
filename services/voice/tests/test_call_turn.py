"""Unit tests for call.turn.TurnOrchestrator — turn dispatch, D1 fault
tolerance guard, and call termination — using fakes for its collaborators
so these are true unit tests (the live-WS D1/D2 behavior is covered
end-to-end by tests/test_ws_fault_tolerance.py)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from call.egress import EgressSender
from call.events import CallContext
from call.media import MediaRouter
from call.turn import TurnOrchestrator
from runtime.session import SessionState


class _FakeAdapter:
    name = "fake"

    def encode_outbound(self, payload):  # noqa: ANN001
        return [payload]

    async def on_call_end(self, reason, session_id):  # noqa: ANN001
        self.last_end = (reason, session_id)


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, msg) -> None:  # noqa: ANN001
        self.sent.append(msg)


class _FakeDialogue:
    """Stands in for call.dialogue.DialogueEngine — records calls."""

    def __init__(self) -> None:
        self.handled: list[str] = []
        self.filler_selector = SimpleNamespace(
            next_audio_for_emotion=lambda label: ("", None),
            next_audio=lambda ctx: ("", None),
        )

    async def handle_turn(self, utterance, turn, t_start, state, tts_interrupt, escalate):  # noqa: ANN001
        self.handled.append(utterance)

    async def rag_lookup(self, utterance, gender):  # noqa: ANN001
        return None


def _make_orchestrator(exec_mode: str = "fsm") -> tuple[TurnOrchestrator, _FakeWS, _FakeAdapter, _FakeDialogue]:
    ws = _FakeWS()
    adapter = _FakeAdapter()
    egress = EgressSender(ws, adapter)  # type: ignore[arg-type]
    media = MediaRouter(session_id="s1")
    dialogue = _FakeDialogue()
    ctx = CallContext(session_id="s1", script={"execution_mode": exec_mode, "steps": []})
    settings = SimpleNamespace(
        question_timeout_seconds=60,
        voice_worker_base_url="http://x",
        notify_platform="none",
        telegram_bot_token="",
        telegram_group_id="",
        redis_url="redis://localhost:6379",
    )
    orch = TurnOrchestrator(
        egress, media, dialogue, ctx, None,  # type: ignore[arg-type]
        nlu=None, tts_chain=None, tts=None, settings=settings,
    )
    return orch, ws, adapter, dialogue


# ── process_utterance dispatch ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_utterance_noop_when_no_state():
    orch, ws, _, dialogue = _make_orchestrator()

    await orch.process_utterance("hi", 0.0)

    assert dialogue.handled == []
    assert ws.sent == []


@pytest.mark.asyncio
async def test_process_utterance_routes_rag_assisted_scripts_to_dialogue():
    orch, _, _, dialogue = _make_orchestrator(exec_mode="rag_assisted")
    orch.state = SessionState(session_id="s1", script_id="scr", current_step_id="greeting")

    await orch.process_utterance("câu hỏi", 0.0)

    assert dialogue.handled == ["câu hỏi"]
    assert orch.turn == 1
    assert orch.tts_active is False  # reset after handling


# ── end_call / speak_fallback_and_end_call ──────────────────────────────────


@pytest.mark.asyncio
async def test_end_call_sends_hangup_and_runs_adapter_side_effect():
    orch, ws, adapter, _ = _make_orchestrator()
    orch.state = SessionState(session_id="s1", script_id="scr", current_step_id="greeting")

    await orch.end_call("hangup", "greeting")

    assert orch.call_ended.is_set()
    assert any(m.get("event") == "hangup" for m in ws.sent)
    assert adapter.last_end == ("hangup", "s1")


@pytest.mark.asyncio
async def test_end_call_sends_handoff_payload_for_handoff_reason():
    orch, ws, adapter, _ = _make_orchestrator()

    await orch.end_call("handoff", "handoff_step")

    assert any(m.get("event") == "handoff" for m in ws.sent)
    assert adapter.last_end == ("handoff", "s1")


@pytest.mark.asyncio
async def test_speak_fallback_and_end_call_is_a_noop_once_call_already_ended():
    orch, ws, _, _ = _make_orchestrator()
    orch.call_ended.set()

    await orch.speak_fallback_and_end_call()

    assert ws.sent == []  # nothing sent — already ended


@pytest.mark.asyncio
async def test_speak_fallback_and_end_call_speaks_then_hangs_up():
    orch, ws, adapter, _ = _make_orchestrator()
    orch.state = SessionState(session_id="s1", script_id="scr", current_step_id="greeting")

    await orch.speak_fallback_and_end_call()

    assert orch.call_ended.is_set()
    beat_texts = [m.get("text") for m in ws.sent if m.get("event") == "beat"]
    assert any("sự cố kỹ thuật" in (t or "") for t in beat_texts)
    assert any(m.get("event") == "hangup" for m in ws.sent)
    assert adapter.last_end == ("hangup", "s1")


@pytest.mark.asyncio
async def test_speak_fallback_and_end_call_forces_call_ended_even_if_end_call_raises(monkeypatch):
    orch, _, _, _ = _make_orchestrator()
    orch.state = SessionState(session_id="s1", script_id="scr", current_step_id="greeting")

    async def _boom(reason, step_id):  # noqa: ANN001
        raise RuntimeError("adapter is on fire")

    monkeypatch.setattr(orch, "end_call", _boom)

    await orch.speak_fallback_and_end_call()  # must not raise

    assert orch.call_ended.is_set()


# ── D1: turn_handler exception guard (unit-level, no live WS) ──────────────


@pytest.mark.asyncio
async def test_turn_handler_survives_process_utterance_exception():
    orch, ws, adapter, _ = _make_orchestrator()
    orch.state = SessionState(session_id="s1", script_id="scr", current_step_id="greeting")

    async def _boom(*args, **kwargs):  # noqa: ANN001
        raise RuntimeError("simulated failure")

    orch.process_utterance = _boom  # type: ignore[method-assign]
    await orch.on_transcript("bất kỳ", None)

    handler_task = asyncio.create_task(orch.turn_handler())
    await asyncio.wait_for(orch.call_ended.wait(), timeout=2.0)
    handler_task.cancel()

    assert orch.call_ended.is_set()
    assert any(m.get("event") == "hangup" for m in ws.sent)


# ── inbound feed queuing ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_on_transcript_and_on_answer_enqueue():
    orch, _, _, _ = _make_orchestrator()

    await orch.on_transcript("xin chào", "happy")
    await orch.on_answer("q1", "câu trả lời")

    assert orch.transcript_queue.qsize() == 1
    assert orch.answer_queue.qsize() == 1
