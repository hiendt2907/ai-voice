"""Unit tests for call.dialogue.DialogueEngine (RAG-assisted turn handling +
mid-FSM RAG lookup primitive)."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import rag.store as rag_store_module
from call.dialogue import DialogueEngine
from call.egress import EgressSender
from call.events import CallContext
from llm.conversation import REFUSAL_SENTINEL
from runtime.session import SessionState, TranscriptEntry
from tts.fillers import FillerSelector


class _FakeEgress:
    """Records calls instead of touching a real WebSocket/adapter."""

    def __init__(self) -> None:
        self.said: list[tuple[str, int, str]] = []
        self.fillers: list[tuple[str, int]] = []

    async def say(self, text, turn, t_start, step_id, tts_chain, tts):  # noqa: ANN001
        self.said.append((text, turn, step_id))

    async def emit_filler(self, filler_text, filler_pcm, turn, t_start, step_id, tts_chain, tts):  # noqa: ANN001
        self.fillers.append((filler_text, turn))

    async def send_beat(self, beat):  # noqa: ANN001
        pass

    async def send_audio(self, pcm_bytes, turn):  # noqa: ANN001
        pass


@dataclass
class _FakeArticle:
    id: str = "art-1"
    tags: list[str] = field(default_factory=list)
    category: str | None = None


@dataclass
class _FakeRagResult:
    answer: str
    score: float
    article: _FakeArticle


def _make_dialogue(egress: _FakeEgress, ctx: CallContext) -> DialogueEngine:
    return DialogueEngine(
        egress,  # type: ignore[arg-type]
        ctx,
        conv_engine=None,
        tts_chain=None,
        tts=None,
        filler_selector=FillerSelector(),
        kb_grounding_enabled=False,
        max_history_turns=5,
        sentence_split_min_chars=20,
        rag_confidence_default=0.6,
    )


# ── get_history ─────────────────────────────────────────────────────────────


def test_get_history_returns_empty_for_no_state():
    dialogue = _make_dialogue(_FakeEgress(), CallContext())

    assert dialogue.get_history(None) == []


def test_get_history_pairs_user_then_agent_entries():
    state = SessionState(session_id="s1", script_id="scr", current_step_id="step1")
    state = state.with_transcript_entry(TranscriptEntry(step_id="step1", role="user", text="hi"))
    state = state.with_transcript_entry(TranscriptEntry(step_id="step1", role="agent", text="hello"))
    state = state.with_transcript_entry(TranscriptEntry(step_id="step2", role="user", text="bye"))
    state = state.with_transcript_entry(TranscriptEntry(step_id="step2", role="agent", text="goodbye"))

    dialogue = _make_dialogue(_FakeEgress(), CallContext())

    assert dialogue.get_history(state) == [("hi", "hello"), ("bye", "goodbye")]


def test_get_history_respects_max_history_turns():
    state = SessionState(session_id="s1", script_id="scr", current_step_id="step1")
    for i in range(5):
        state = state.with_transcript_entry(TranscriptEntry(step_id="s", role="user", text=f"u{i}"))
        state = state.with_transcript_entry(TranscriptEntry(step_id="s", role="agent", text=f"a{i}"))

    egress = _FakeEgress()
    dialogue = DialogueEngine(
        egress, CallContext(),  # type: ignore[arg-type]
        conv_engine=None, tts_chain=None, tts=None,
        filler_selector=FillerSelector(), kb_grounding_enabled=False,
        max_history_turns=2, sentence_split_min_chars=20, rag_confidence_default=0.6,
    )

    history = dialogue.get_history(state)

    assert history == [("u3", "a3"), ("u4", "a4")]


# ── rag_lookup ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rag_lookup_uses_cache_hit_without_embedding(monkeypatch):
    ctx = CallContext(campaign_id="camp-1")
    dialogue = _make_dialogue(_FakeEgress(), ctx)
    cached = _FakeRagResult(answer="cached answer", score=0.9, article=_FakeArticle())

    cache_lookup = AsyncMock(return_value=cached)
    search = AsyncMock(side_effect=AssertionError("search should not be called on cache hit"))
    monkeypatch.setattr(rag_store_module, "cache_lookup", cache_lookup)
    monkeypatch.setattr(rag_store_module, "search", search)

    result = await dialogue.rag_lookup("câu hỏi", "unknown")

    assert result is cached
    cache_lookup.assert_awaited_once_with("câu hỏi", "camp-1", "unknown")
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_rag_lookup_falls_back_to_embed_and_search_on_cache_miss(monkeypatch):
    ctx = CallContext(campaign_id="camp-1")
    dialogue = _make_dialogue(_FakeEgress(), ctx)
    searched = _FakeRagResult(answer="searched answer", score=0.75, article=_FakeArticle())

    monkeypatch.setattr(rag_store_module, "cache_lookup", AsyncMock(return_value=None))
    search = AsyncMock(return_value=searched)
    monkeypatch.setattr(rag_store_module, "search", search)
    import rag.embedder as embedder_module
    monkeypatch.setattr(embedder_module, "embed_query", lambda text: [0.1, 0.2])

    result = await dialogue.rag_lookup("câu hỏi", "male")

    assert result is searched
    search.assert_awaited_once()


@pytest.mark.asyncio
async def test_rag_lookup_returns_none_on_error(monkeypatch):
    ctx = CallContext(campaign_id="camp-1")
    dialogue = _make_dialogue(_FakeEgress(), ctx)

    async def _boom(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(rag_store_module, "cache_lookup", _boom)

    result = await dialogue.rag_lookup("câu hỏi", "unknown")

    assert result is None


# ── handle_turn (rag_assisted mode) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_turn_shadow_mode_does_not_speak(monkeypatch):
    ctx = CallContext(interception_mode="shadow", campaign_id="c1")
    egress = _FakeEgress()
    dialogue = _make_dialogue(egress, ctx)
    hit = _FakeRagResult(answer="would say this", score=0.9, article=_FakeArticle())
    monkeypatch.setattr(rag_store_module, "cache_lookup", AsyncMock(return_value=hit))

    escalate = AsyncMock()
    tts_interrupt = SimpleNamespace()  # unused by shadow path
    import asyncio
    await dialogue.handle_turn("câu hỏi", 1, 0.0, None, asyncio.Event(), escalate)

    assert egress.said == []
    assert ctx.last_rag_score == 0.9
    escalate.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_turn_speaks_rag_answer_when_no_conv_engine(monkeypatch):
    ctx = CallContext(interception_mode="full", campaign_id="c1")
    egress = _FakeEgress()
    dialogue = _make_dialogue(egress, ctx)
    hit = _FakeRagResult(answer="the answer", score=0.9, article=_FakeArticle())
    monkeypatch.setattr(rag_store_module, "cache_lookup", AsyncMock(return_value=hit))

    import asyncio
    await dialogue.handle_turn("câu hỏi", 1, 0.0, None, asyncio.Event(), AsyncMock())

    assert egress.said == [("the answer", 1, "")]


@pytest.mark.asyncio
async def test_handle_turn_escalates_on_no_match(monkeypatch):
    ctx = CallContext(interception_mode="full", campaign_id="c1")
    egress = _FakeEgress()
    dialogue = _make_dialogue(egress, ctx)  # conv_engine=None — reasoning tier off
    monkeypatch.setattr(rag_store_module, "cache_lookup", AsyncMock(return_value=None))
    monkeypatch.setattr(rag_store_module, "fallback_text", lambda gender: "fallback msg")

    escalate = AsyncMock()
    state = SessionState(session_id="s1", script_id="scr", current_step_id="step1")
    import asyncio
    await dialogue.handle_turn("câu hỏi lạ", 1, 0.0, state, asyncio.Event(), escalate)

    assert egress.said == [("fallback msg", 1, "step1")]
    assert ctx.last_rag_score == 0.0
    escalate.assert_awaited_once_with("câu hỏi lạ")


# ── handle_turn — Tầng 3 reasoning tier (RAG miss, conv_engine present) ─────


class _FakeConvEngine:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self.calls: list[dict] = []

    def stream_response(self, utterance, kb_context, history, emotion):  # noqa: ANN001
        self.calls.append({"utterance": utterance, "kb_context": kb_context})

        async def _gen():
            for t in self._tokens:
                yield t

        return _gen()


def _make_reasoning_dialogue(egress: _FakeEgress, ctx: CallContext, conv_engine) -> DialogueEngine:
    return DialogueEngine(
        egress,  # type: ignore[arg-type]
        ctx,
        conv_engine=conv_engine,
        tts_chain=None,
        tts=None,
        filler_selector=FillerSelector(),
        kb_grounding_enabled=True,
        max_history_turns=5,
        sentence_split_min_chars=20,
        rag_confidence_default=0.6,
        rag_context_floor=0.45,
    )


@pytest.mark.asyncio
async def test_handle_turn_reasons_when_rag_misses_but_loose_context_found(monkeypatch):
    ctx = CallContext(interception_mode="full", campaign_id="c1")
    egress = _FakeEgress()
    conv_engine = _FakeConvEngine(["Dạ phòng khám ", "mở cửa cả thứ Bảy ạ."])
    dialogue = _make_reasoning_dialogue(egress, ctx, conv_engine)

    monkeypatch.setattr(rag_store_module, "cache_lookup", AsyncMock(return_value=None))
    loose_hit = _FakeRagResult(answer="Giờ làm việc: T2-T7", score=0.5, article=_FakeArticle())

    async def _search(*args, max_threshold, **kwargs):  # noqa: ANN001
        # Strict lookup (rag_confidence_default=0.6) misses; only the loose
        # floor (rag_context_floor=0.45) call should surface this article.
        return loose_hit if max_threshold <= 0.45 else None

    monkeypatch.setattr(rag_store_module, "search", _search)
    import rag.embedder as embedder_module
    monkeypatch.setattr(embedder_module, "embed_query", lambda text: [0.1, 0.2])

    escalate = AsyncMock()
    state = SessionState(session_id="s1", script_id="scr", current_step_id="step1")
    import asyncio
    await dialogue.handle_turn("thứ bảy có làm việc không", 1, 0.0, state, asyncio.Event(), escalate)

    assert conv_engine.calls == [
        {"utterance": "thứ bảy có làm việc không", "kb_context": "Giờ làm việc: T2-T7"}
    ]
    escalate.assert_not_awaited()
    assert egress.said == []  # tts_chain=None -> beat-only path, not egress.say


@pytest.mark.asyncio
async def test_handle_turn_reasoning_refusal_escalates(monkeypatch):
    ctx = CallContext(interception_mode="full", campaign_id="c1")
    egress = _FakeEgress()
    conv_engine = _FakeConvEngine([REFUSAL_SENTINEL])
    dialogue = _make_reasoning_dialogue(egress, ctx, conv_engine)

    monkeypatch.setattr(rag_store_module, "cache_lookup", AsyncMock(return_value=None))
    loose_hit = _FakeRagResult(answer="context không đủ liên quan", score=0.46, article=_FakeArticle())

    async def _search(*args, max_threshold, **kwargs):  # noqa: ANN001
        return loose_hit if max_threshold <= 0.45 else None

    monkeypatch.setattr(rag_store_module, "search", _search)
    import rag.embedder as embedder_module
    monkeypatch.setattr(embedder_module, "embed_query", lambda text: [0.1, 0.2])
    monkeypatch.setattr(rag_store_module, "fallback_text", lambda gender: "fallback msg")

    escalate = AsyncMock()
    state = SessionState(session_id="s1", script_id="scr", current_step_id="step1")
    import asyncio
    await dialogue.handle_turn("câu hỏi khó", 1, 0.0, state, asyncio.Event(), escalate)

    escalate.assert_awaited_once_with("câu hỏi khó")
    # the refusal line was already "spoken" (accumulated) -> no double fallback message
    assert egress.said == []


@pytest.mark.asyncio
async def test_handle_turn_blacklisted_utterance_skips_llm(monkeypatch):
    ctx = CallContext(interception_mode="full", campaign_id="c1")
    egress = _FakeEgress()
    conv_engine = _FakeConvEngine(["should never be called"])
    dialogue = _make_reasoning_dialogue(egress, ctx, conv_engine)

    monkeypatch.setattr(rag_store_module, "cache_lookup", AsyncMock(return_value=None))
    monkeypatch.setattr(rag_store_module, "fallback_text", lambda gender: "fallback msg")
    monkeypatch.setattr(rag_store_module, "diagnosis_escalation_text", lambda gender: "doctor callback msg")
    search = AsyncMock(side_effect=AssertionError("must not reach RAG search for blacklisted input"))
    monkeypatch.setattr(rag_store_module, "search", search)

    escalate = AsyncMock()
    state = SessionState(session_id="s1", script_id="scr", current_step_id="step1")
    import asyncio
    await dialogue.handle_turn("bác sĩ chẩn đoán giúp em", 1, 0.0, state, asyncio.Event(), escalate)

    assert conv_engine.calls == []
    # blacklisted (diagnosis) input must get the doctor-callback line, not
    # the generic RAG-miss fallback — distinct spoken message on purpose.
    assert egress.said == [("doctor callback msg", 1, "step1")]
    escalate.assert_awaited_once_with("bác sĩ chẩn đoán giúp em")


@pytest.mark.asyncio
async def test_handle_turn_no_loose_context_falls_back(monkeypatch):
    ctx = CallContext(interception_mode="full", campaign_id="c1")
    egress = _FakeEgress()
    conv_engine = _FakeConvEngine(["should never be called"])
    dialogue = _make_reasoning_dialogue(egress, ctx, conv_engine)

    monkeypatch.setattr(rag_store_module, "cache_lookup", AsyncMock(return_value=None))
    monkeypatch.setattr(rag_store_module, "search", AsyncMock(return_value=None))
    monkeypatch.setattr(rag_store_module, "fallback_text", lambda gender: "fallback msg")
    import rag.embedder as embedder_module
    monkeypatch.setattr(embedder_module, "embed_query", lambda text: [0.1, 0.2])

    escalate = AsyncMock()
    state = SessionState(session_id="s1", script_id="scr", current_step_id="step1")
    import asyncio
    await dialogue.handle_turn("câu hỏi hoàn toàn ngoài phạm vi", 1, 0.0, state, asyncio.Event(), escalate)

    assert conv_engine.calls == []
    assert egress.said == [("fallback msg", 1, "step1")]
    escalate.assert_awaited_once_with("câu hỏi hoàn toàn ngoài phạm vi")


# ── _tts_stream cancellation (barge-in must close the LLM stream, not just
# stop consuming it — see call/dialogue.py::_tts_stream docstring/comment) ──


class _FakeTTSChain:
    def primary_engine_name(self) -> str:
        return "fake"

    async def stream_synthesize(self, text, params):  # noqa: ANN001
        async def _gen():
            yield b"chunk"
        return _gen()


@pytest.mark.asyncio
async def test_tts_stream_acloses_generator_on_interrupt():
    from tts.params import EmotionState

    ctx = CallContext()
    egress = _FakeEgress()
    dialogue = _make_dialogue(egress, ctx)
    dialogue.tts_chain = _FakeTTSChain()  # type: ignore[assignment]

    closed: list[bool] = []
    interrupt = __import__("asyncio").Event()

    async def _tokens():
        yield "xin chào, "
        interrupt.set()  # barge-in happens mid-stream
        yield "phần này không nên được nói."

    async def _gen_with_finally():
        try:
            async for t in _tokens():
                yield t
        finally:
            closed.append(True)

    await dialogue._tts_stream(_gen_with_finally(), 1, 0.0, EmotionState("neutral"), interrupt, None)

    assert closed == [True]  # aclose() reached the generator's finally block


@pytest.mark.asyncio
async def test_tts_stream_acloses_generator_on_natural_completion():
    """aclose() on an already-exhausted generator must be a harmless no-op —
    the fix must not break the non-interrupted path."""
    from tts.params import EmotionState

    ctx = CallContext()
    egress = _FakeEgress()
    dialogue = _make_dialogue(egress, ctx)
    dialogue.tts_chain = _FakeTTSChain()  # type: ignore[assignment]

    async def _tokens():
        yield "câu trả lời đầy đủ."

    # Must complete without raising (aclose() on an exhausted generator is
    # required by the async-generator protocol to be a silent no-op).
    await dialogue._tts_stream(
        _tokens(), 1, 0.0, EmotionState("neutral"), __import__("asyncio").Event(), None
    )
