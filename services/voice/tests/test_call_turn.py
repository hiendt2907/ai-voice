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
from call.turn import _QUESTION_RE, TurnOrchestrator, _resolves_to_graceful_close
from runtime.executor import TurnResult
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
        tts_chain=None, tts=None, settings=settings,
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


# ── status classification (booking_success mislabelled "error" bug) ────────
#
# 267 cuộc gọi đặt lịch thành công từng bị ghi status="error" vì step
# booking_success có type "speak_listen" (vẫn lắng nghe xem khách còn cần gì
# thêm không), nên khi khách cúp máy ở đó, state.status không bao giờ được
# set thành "completed" — _post_call_events (ws.py) map mọi status khác
# "completed"/"handoff" thành "error". Các test dưới đây chứng minh
# call.turn._resolves_to_graceful_close() phân biệt đúng ba trường hợp mà
# KHÔNG hardcode step id "booking_success" — chỉ dựa vào fallback_goto của
# chính step đó trỏ tới step "speak"/"hangup" (kết thúc êm) hay "handoff"
# (còn dở dang, cần người thật).

_GRACEFUL_CLOSE_STEPS: dict[str, dict] = {
    "booking_success": {
        "id": "booking_success",
        "type": "speak_listen",
        "fallback_goto": "farewell",
        "variants": [{"beats": [{"text": "Dạ, em đặt lịch xong rồi ạ.", "pause_after": "turn"}]}],
    },
    "farewell": {
        "id": "farewell",
        "type": "speak",
        "variants": [{"beats": [{"text": "Chúc anh chị sức khỏe ạ.", "pause_after": "long"}]}],
    },
    "collect_patient_info": {
        "id": "collect_patient_info",
        "type": "speak_listen",
        "fallback_goto": "handoff_to_staff",
        "variants": [{"beats": [{"text": "Cho em xin tên anh chị ạ.", "pause_after": "turn"}]}],
    },
    "handoff_to_staff": {
        "id": "handoff_to_staff",
        "type": "handoff",
        "variants": [{"beats": [{"text": "Em xin phép chuyển máy ạ.", "pause_after": "turn"}]}],
    },
}


def _fake_async_process_turn(next_step_id: str):
    """Stand-in for runtime.executor.async_process_turn: skips real NLU/vector
    matching entirely and just transitions state.current_step_id straight to
    `next_step_id`, the way a genuine FSM transition would after matching an
    intent. What's under test is call.turn's post-transition status logic,
    not the NLU layer."""

    async def _fake(state, script_body, utterance):  # noqa: ANN001
        new_state = state.with_step(next_step_id)
        return TurnResult(
            agent_text="", intent="some_intent", slots={}, next_step_id=next_step_id,
            is_handoff=False, is_completed=False, state=new_state,
        )

    return _fake


@pytest.mark.asyncio
async def test_speak_listen_step_resolving_to_graceful_close_marks_completed(monkeypatch):
    """(a) booking_success-like step (speak_listen, fallback_goto -> farewell
    whose type is "speak") reached, khách rồi cúp máy -> status phải là
    "completed", không phải "active" (mà ws.py sẽ map thành "error")."""
    orch, _, _, _ = _make_orchestrator()
    orch.ctx.steps = _GRACEFUL_CLOSE_STEPS
    orch.state = SessionState(session_id="s1", script_id="scr", current_step_id="confirm_booking")
    monkeypatch.setattr("call.turn.async_process_turn", _fake_async_process_turn("booking_success"))

    await orch.process_utterance("vâng đúng rồi ạ", 0.0)

    assert orch.state is not None
    assert orch.state.current_step_id == "booking_success"
    assert orch.state.status == "completed"
    # speak_listen vẫn đang lắng nghe — cuộc gọi KHÔNG kết thúc ngay lượt này.
    assert not orch.call_ended.is_set()


@pytest.mark.asyncio
async def test_speak_listen_step_falling_back_to_handoff_stays_active(monkeypatch):
    """(b) đứt giữa chừng ở bước thu thập thông tin (fallback_goto trỏ tới
    step "handoff", không phải "speak"/"hangup") -> status phải KHÔNG được
    đổi thành "completed" — vẫn "active" nên _post_call_events tiếp tục ghi
    nhận đúng là "error" (dở dang thật sự, không phải lỗi giả)."""
    orch, _, _, _ = _make_orchestrator()
    orch.ctx.steps = _GRACEFUL_CLOSE_STEPS
    orch.state = SessionState(session_id="s1", script_id="scr", current_step_id="confirm_time_available")
    monkeypatch.setattr("call.turn.async_process_turn", _fake_async_process_turn("collect_patient_info"))

    await orch.process_utterance("tôi tên là Hiền", 0.0)

    assert orch.state is not None
    assert orch.state.current_step_id == "collect_patient_info"
    assert orch.state.status == "active"
    assert not orch.call_ended.is_set()


@pytest.mark.asyncio
async def test_landing_on_handoff_step_marks_handoff_status(monkeypatch):
    """(c) Chuyển thẳng tới step type "handoff" -> status phải là "handoff",
    và cuộc gọi kết thúc bằng end_call("handoff", ...) ngay lượt đó."""
    orch, ws, adapter, _ = _make_orchestrator()
    orch.ctx.steps = _GRACEFUL_CLOSE_STEPS
    orch.state = SessionState(session_id="s1", script_id="scr", current_step_id="collect_patient_info")
    monkeypatch.setattr("call.turn.async_process_turn", _fake_async_process_turn("handoff_to_staff"))

    await orch.process_utterance("cho tôi gặp nhân viên", 0.0)

    assert orch.state is not None
    assert orch.state.current_step_id == "handoff_to_staff"
    assert orch.state.status == "handoff"
    assert orch.call_ended.is_set()
    assert adapter.last_end == ("handoff", "s1")


# ── _resolves_to_graceful_close: pure structural criterion ─────────────────


def test_resolves_to_graceful_close_true_when_fallback_is_speak():
    steps = _GRACEFUL_CLOSE_STEPS
    assert _resolves_to_graceful_close(steps["booking_success"], steps) is True


def test_resolves_to_graceful_close_false_when_fallback_is_handoff():
    steps = _GRACEFUL_CLOSE_STEPS
    assert _resolves_to_graceful_close(steps["collect_patient_info"], steps) is False


def test_resolves_to_graceful_close_false_when_no_fallback_goto():
    step = {"id": "no_fallback", "type": "speak_listen"}
    assert _resolves_to_graceful_close(step, _GRACEFUL_CLOSE_STEPS) is False


def test_resolves_to_graceful_close_follows_transitive_speak_listen_chain():
    """fallback_goto có thể trỏ tới một speak_listen KHÁC trước khi tới
    step "speak" cuối cùng — vẫn phải resolve True (đi qua chuỗi, không chỉ
    nhìn một bước)."""
    steps = {
        "mid": {"id": "mid", "type": "speak_listen", "fallback_goto": "farewell"},
        "farewell": {"id": "farewell", "type": "speak"},
    }
    step = {"id": "start", "type": "speak_listen", "fallback_goto": "mid"}
    assert _resolves_to_graceful_close(step, steps) is True


def test_resolves_to_graceful_close_handles_cycle_without_infinite_recursion():
    """fallback_goto trỏ vòng lại chính nó (kịch bản lỗi cấu hình) không được
    làm treo recursion — phải trả về False."""
    steps = {"loop": {"id": "loop", "type": "speak_listen", "fallback_goto": "loop"}}
    step = steps["loop"]
    assert _resolves_to_graceful_close(step, steps) is False


# ── _QUESTION_RE — regression cases from the 100-call LLM-caller audit ─────
#
# Mỗi câu dưới đây từng bị AI bỏ qua trong bộ 100 cuộc gọi giả lập
# (llm_conversation_results_100.json) vì _QUESTION_RE không nhận diện được
# là câu hỏi, nên _fsm_rag_intercept không bao giờ thử RAG search. Đã xác
# nhận bằng /rag/test-search thật trên GCP rằng cả hai đều có điểm vượt
# ngưỡng trả lời trực tiếp rag_confidence_default=0.65 (0.6783 và 0.6960 —
# xem báo cáo điều tra), nghĩa là nếu regex bắt được, AI đã trả lời đúng.


def test_question_re_matches_question_mark_mid_utterance_not_only_at_end():
    """Neo `\\?$` cũ chỉ khớp khi "?" là ký tự cuối chuỗi — bỏ sót câu hỏi
    thật khi caller nói tiếp sau dấu hỏi trong cùng một lượt (rất phổ biến
    với STT/LLM caller ghép nhiều câu liền nhau)."""
    utterance = (
        "Mới rồi em có nghe nói bệnh viện này có dịch vụ khám tổng quát "
        "phải không? Em muốn hỏi xem cái dịch vụ ấy..."
    )
    assert _QUESTION_RE.search(utterance) is not None


def test_question_re_matches_muon_hoi_intent_phrase_without_question_mark():
    """"muốn hỏi" là tín hiệu ý định hỏi rõ ràng trong tiếng Việt dù câu
    không kết bằng dấu "?" — ví dụ khách nói ý định hỏi trước khi đặt câu
    hỏi cụ thể."""
    utterance = "Tôi muốn hỏi trước về nội soi dạ dày trước đã. Chứ chưa đặt lịch ạ."
    assert _QUESTION_RE.search(utterance) is not None


def test_question_re_still_ignores_plain_booking_statement():
    """Câu trần thuật đặt lịch thông thường, không có dấu hiệu câu hỏi nào,
    không được kích hoạt RAG search — tránh regression ngược, quét quá rộng."""
    utterance = "Dạ, em muốn đặt lịch khám da liễu cho em bé nhà em ạ."
    assert _QUESTION_RE.search(utterance) is None
