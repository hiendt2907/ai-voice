"""TurnOrchestrator — one call's turn-by-turn dialogue loop.

Owns the mutable per-call FSM `SessionState`, drains transcripts +
Phase-3 doctor answers, and decides which path handles a turn:
  - `execution_mode: "rag_assisted"` -> `call.dialogue.DialogueEngine`
  - everything else (default) -> the FSM (`runtime.executor`,
    `runtime.fsm` — untouched, called exactly as `ws.py` used to) with
    mid-conversation RAG interception for questions the FSM doesn't route.

This is also where the D1/D2 fault-tolerance patches live: `turn_handler`
guards every `process_utterance` call (D1 — an unguarded exception used to
kill this loop permanently, leaving the caller on a silent, hung line), and
`speak_fallback_and_end_call` is the shared "stop the bleeding" path used
both here and by `call.media.MediaRouter` on an unrecoverable STT failure
(D2).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from call.dialogue import DialogueEngine
from call.egress import EgressSender
from call.events import CallContext, HandoffPayload, HangupPayload
from call.handoff import HandoffCoordinator
from call.media import MediaRouter
from call.session import ActiveCall
from obs import tracing as obs
from obs.turn_trace import TurnTrace
from runtime.executor import async_process_turn
from runtime.session import SessionState

logger = logging.getLogger(__name__)

_FALLBACK_ERROR_MESSAGE = (
    "Dạ hệ thống đang gặp sự cố kỹ thuật, xin quý khách vui lòng gọi lại sau ít phút ạ."
)

def _render_step_text(step: dict, slots: dict[str, str]) -> str:
    """Flatten a step's beats into the sentence the caller actually hears,
    with {{slot}} substituted — the trace should show the spoken text, not
    the template."""
    variants = step.get("variants") or []
    beats = variants[0].get("beats", []) if variants else []
    out: list[str] = []
    for beat in beats:
        text = beat.get("text", "")
        for key, value in slots.items():
            text = text.replace("{{" + key + "}}", str(value))
        if text.strip():
            out.append(text.strip())
    return " ".join(out)


_QUESTION_RE = re.compile(
    r"\?$"
    r"|\b(bao nhiêu|mấy tiếng|như thế nào|ra sao|thế nào|là gì|ở đâu|khi nào|làm gì|cần gì)\b"
    r"|\bcó\b.{0,25}\bkhông\b"
    r"|\bcòn\b.{0,20}\b(trống|lịch|chỗ|không|được)\b"
    r"|\b(giờ nào|khung giờ|mấy giờ).{0,20}\b(còn|trống|được|có)\b"
    r"|\b(giá|chi phí|phí|chuẩn bị|nhịn ăn|đau không|an toàn|nguy hiểm|kết quả|bảo hiểm"
    r"|mất bao|sau nội soi|sau khi|thuốc|tác dụng|giờ làm việc|lịch làm việc|mở cửa)\b",
    re.IGNORECASE | re.DOTALL,
)


class TurnOrchestrator:
    def __init__(
        self,
        egress: EgressSender,
        media: MediaRouter,
        dialogue: DialogueEngine,
        ctx: CallContext,
        active_call: ActiveCall | None,
        *,
        nlu: object | None,
        tts_chain: object | None,
        tts: object | None,
        settings: Any,
    ) -> None:
        self.egress = egress
        self.media = media
        self.dialogue = dialogue
        self.ctx = ctx
        self.active_call = active_call
        self.nlu = nlu
        self.tts_chain = tts_chain
        self.tts = tts
        self.settings = settings

        self.state: SessionState | None = None
        self.turn = 0
        self.tts_active = False
        # Set by MediaRouter on each final transcript; read when the turn's
        # trace is opened, since process_utterance only receives the text.
        self.last_stt_confidence: float | None = None
        # Last RAG SearchResult of the current turn, folded into its trace.
        self._last_rag: Any = None
        self.tts_interrupt = asyncio.Event()
        self.call_ended = asyncio.Event()

        self.transcript_queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
        self.answer_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        self.handoff = HandoffCoordinator(
            self, egress, ctx, tts_chain=tts_chain, tts=tts, settings=settings,
        )

    @property
    def pending_question_tasks(self) -> list[asyncio.Task]:
        return self.handoff.pending_question_tasks

    # ── inbound feeds (called by ws.py event loop / MediaRouter) ──────────

    async def on_transcript(
        self, text: str, stt_emotion: str | None, confidence: float | None = None
    ) -> None:
        # Confidence rides alongside rather than through the queue so the
        # existing (text, emotion) contract with MediaRouter is unchanged.
        self.last_stt_confidence = confidence
        await self.transcript_queue.put((text, stt_emotion))

    async def on_answer(self, question_id: str, answer: str) -> None:
        await self.answer_queue.put((question_id, answer))

    def start_session(self, state: SessionState) -> None:
        self.state = state

    # ── greeting (was the START-handler tail in ws.py) ─────────────────────

    async def greet(self) -> bool:
        """Send the greeting. Returns True if the call already ended (a
        greeting-only script) — caller should stop reading further events."""
        t0 = time.perf_counter()
        if self.ctx.script_exec_mode() == "rag_assisted":
            greeting_text = self.ctx.script.get("greeting", "Dạ, DoctorCheck xin nghe ạ")
            if greeting_text:
                await self.egress.say(
                    greeting_text, self.turn, t0,
                    self.state.current_step_id if self.state else "", self.tts_chain, self.tts,
                )
            return False

        step = self.ctx.steps.get(self.state.current_step_id, {})  # type: ignore[union-attr]
        await self._stream_step(step, {}, 0, t0)
        if step.get("type") in ("speak", "hangup"):
            await self.end_call("hangup", self.state.current_step_id)  # type: ignore[union-attr]
            return True
        if step.get("type") == "handoff":
            await self.end_call("handoff", self.state.current_step_id)  # type: ignore[union-attr]
            return True
        return False

    # ── turn handler task ───────────────────────────────────────────────

    async def turn_handler(self) -> None:
        while not self.call_ended.is_set():
            while not self.answer_queue.empty():
                qid, ans = self.answer_queue.get_nowait()
                try:
                    await self.handoff.inject_answer(qid, ans)
                except Exception:
                    logger.exception(
                        "turn_handler: inject_answer failed session_id=%s question_id=%s",
                        self.ctx.session_id, qid,
                    )

            try:
                text, stt_emotion = await asyncio.wait_for(self.transcript_queue.get(), timeout=0.5)
            except TimeoutError:
                continue

            t0 = time.perf_counter()
            # D1: process_utterance previously ran with no exception guard —
            # any exception (RAG error, TTS chain exhaustion, Redis blip, ...)
            # killed this task permanently, leaving the WS open and the
            # caller met with silence forever. Guard it, log with session
            # context, and end the call cleanly with a spoken fallback.
            try:
                await self.process_utterance(text, t0, stt_emotion)
            except Exception:
                logger.exception(
                    "turn_handler: unhandled exception processing utterance "
                    "session_id=%s turn=%s text=%r",
                    self.ctx.session_id, self.turn, text,
                )
                await self.speak_fallback_and_end_call()

    # ── main turn dispatch ──────────────────────────────────────────────

    async def process_utterance(
        self, utterance: str, t_start: float, stt_emotion: str | None = None
    ) -> None:
        if self.state is None:
            return

        if stt_emotion is not None and stt_emotion not in ("neutral", "unk"):
            self.state = self.state.with_emotion(stt_emotion)

        if self.ctx.script_exec_mode() == "rag_assisted":
            self.tts_active = True
            self.tts_interrupt.clear()
            self.turn += 1
            await self.dialogue.handle_turn(
                utterance, self.turn, t_start, self.state, self.tts_interrupt,
                self.handoff.escalate_question,
            )
            self.tts_active = False
            return

        await self._process_fsm_turn(utterance, t_start)

    async def _process_fsm_turn(self, utterance: str, t_start: float) -> None:
        assert self.state is not None
        self.tts_active = True
        self.tts_interrupt.clear()
        self.turn += 1

        # Glassbox: opened here so every decision below can record into it,
        # closed at the end of the turn (see _finish_trace).
        trace = TurnTrace(
            turn=self.turn,
            session_id=self.ctx.session_id,
            stt_text=utterance,
            stt_confidence=self.last_stt_confidence,
            stt_engine=self.ctx.stt_engine_name,
        )

        cur_step = self.ctx.steps.get(self.state.current_step_id, {})
        fillers_disabled = self.ctx.script.get("disable_fillers", False)
        step_filler_ctx: str = cur_step.get("on_receive", {}).get("filler_context", "thinking")

        cur_emotion_label = self.state.current_emotion()
        if fillers_disabled or step_filler_ctx == "none":
            filler_text, filler_pcm = "", None
        elif step_filler_ctx == "thinking":
            filler_text, filler_pcm = self.dialogue.filler_selector.next_audio_for_emotion(cur_emotion_label)
        else:
            filler_text, filler_pcm = self.dialogue.filler_selector.next_audio(step_filler_ctx)  # type: ignore[arg-type]

        filler_task = asyncio.create_task(
            self.egress.emit_filler(
                filler_text, filler_pcm, self.turn, t_start,
                self.state.current_step_id, self.tts_chain, self.tts,
            )
        )
        step_from = self.state.current_step_id
        with obs.span("nlu", parent=self.ctx.otel_ctx, **{"turn": self.turn}) as nlu_span:
            _t_nlu = time.perf_counter()
            result = await async_process_turn(self.state, self.ctx.script, utterance, self.nlu)
            trace.nlu_ms = round((time.perf_counter() - _t_nlu) * 1000, 1)
            trace.nlu_intent = result.intent
            trace.nlu_confidence = result.nlu_confidence
            trace.nlu_tier = result.nlu_tier
            # ~2s cloud round-trip vs a few ms locally — the gap is large
            # enough that "did the LLM run?" is the number worth watching.
            trace.nlu_llm_used = trace.nlu_ms > 500
            obs.set_attr(nlu_span, "nlu.intent", result.intent or "")
            obs.set_attr(nlu_span, "nlu.tier", result.nlu_tier)
            obs.set_attr(nlu_span, "nlu.confidence", result.nlu_confidence)
        self.state = result.state

        await filler_task

        if result.is_handoff:
            step = self.ctx.steps.get(self.state.current_step_id, {})
            await self._stream_step(step, dict(self.state.slots), 0, t_start)
            await self.end_call("handoff", self.state.current_step_id)
            return

        if result.is_completed:
            step = self.ctx.steps.get(self.state.current_step_id, {})
            await self._stream_step(step, dict(self.state.slots), 0, t_start)
            await self.end_call("hangup", self.state.current_step_id)
            return

        if result.next_step_id is None and not result.is_handoff and not result.is_completed:
            rag_answered = await self._fsm_rag_intercept(utterance, t_start)
            if rag_answered:
                step = self.ctx.steps.get(self.state.current_step_id, {})
                no_match = self.state.get_no_match_count(self.state.current_step_id)
                await self._stream_step(step, dict(self.state.slots), no_match, t_start)
                self.tts_active = False
                return
        elif result.next_step_id is not None and _QUESTION_RE.search(utterance):
            # FSM DID transition, but the utterance also contains a question
            # (e.g. "hôm nay còn giờ nào trống") — answer it first, then
            # stream the next FSM step.
            await self._fsm_rag_intercept(utterance, t_start)

        if result.next_step_id is not None:
            step = self.ctx.steps.get(result.next_step_id, {})
            no_match = 0
        else:
            step = self.ctx.steps.get(self.state.current_step_id, {})
            no_match = self.state.get_no_match_count(self.state.current_step_id)

        await self._stream_step(step, dict(self.state.slots), no_match, t_start)

        trace.step_from = step_from
        trace.step_to = step.get("id", self.state.current_step_id)
        trace.slots_new = dict(result.slots)
        trace.agent_text = _render_step_text(step, dict(self.state.slots))
        trace.tts_engine = self.ctx.tts_engine_name
        trace.escalated = result.is_handoff
        await self._finish_trace(trace, t_start)

        # Terminal step reached by *transition* rather than by being the step
        # this turn processed. async_process_turn() only sets state.status when
        # the terminal step is the current one, so on this path the status
        # would otherwise stay "active" — and _post_call_events() maps anything
        # that isn't "completed"/"handoff" to "error", which mislabelled every
        # normally-finished call. Set it here, at the two legitimate terminal
        # landings only; speak_fallback_and_end_call() deliberately leaves the
        # status alone so genuine mid-call failures still persist as "error".
        landed_type = step.get("type", "")
        if landed_type in ("speak", "hangup"):
            if self.state is not None:
                self.state = self.state.with_status("completed")
            await self.end_call("hangup", step.get("id", ""))
            return
        if landed_type == "handoff":
            if self.state is not None:
                self.state = self.state.with_status("handoff")
            await self.end_call("handoff", step.get("id", ""))
            return

        self.tts_active = False

    async def _stream_step(self, step: dict, slots: dict, no_match: int, t_start: float) -> None:
        await self.egress.stream_step(
            step, slots, no_match, self.turn, t_start,
            current_step_id=self.state.current_step_id if self.state else "",
            tts=self.tts,
            tts_interrupt=self.tts_interrupt,
            on_tts_start=self.media.on_tts_start,
            on_tts_end=self.media.on_tts_end,
        )

    async def _finish_trace(self, trace: TurnTrace, t_start: float) -> None:
        """Close the turn's decision record and fan it out: span attributes,
        a live WS event, and the in-memory list persisted on hangup.

        Wrapped so a telemetry problem can never end a call — a failure here
        means a missing trace, not a dropped turn.
        """
        try:
            if self._last_rag is not None:
                trace.rag_hit = True
                trace.rag_score = round(float(self._last_rag.score), 3)
                trace.rag_article_id = str(self._last_rag.article.id)
                trace.rag_article_title = getattr(self._last_rag.article, "title", None)
                self._last_rag = None
            trace.total_ms = round((time.perf_counter() - t_start) * 1000, 1)
            trace.trace_id = self.ctx.trace_id
            # Parented explicitly: this runs in the turn-handler task, where
            # the call span is not in the implicit context.
            with obs.span("turn", parent=self.ctx.otel_ctx) as turn_span:
                trace.apply_to_span(turn_span)
            self.ctx.turn_traces.append(trace.to_dict())
            # Sent AFTER the beats so a live viewer lines the trace up with
            # the audio the caller is hearing.
            await self.egress.send({"event": "turn_trace", **trace.to_dict()})
        except Exception:
            logger.debug("turn trace emit failed", exc_info=True)

    async def _fsm_rag_intercept(self, utterance: str, t_start: float) -> bool:
        """Try RAG for mid-FSM questions. True = RAG answered (caller should
        not increment no_match for this utterance)."""
        if not _QUESTION_RE.search(utterance):
            return False

        gender = self.state.slots.get("gender", "unknown") if self.state else "unknown"  # type: ignore[union-attr]
        result = await self.dialogue.rag_lookup(utterance, gender)
        if result is None:
            return False

        self.ctx.last_rag_score = result.score

        if self.ctx.interception_mode == "shadow":
            logger.info("[SHADOW] FSM would-say: %.80s (score=%.3f)", result.answer, result.score)
            return True  # consumed the turn, no audio

        if self.ctx.interception_mode == "medium" and self.ctx.interception_domains:
            article_tags = set(result.article.tags or [])
            if result.article.category:
                article_tags.add(result.article.category)
            if not article_tags & set(self.ctx.interception_domains):
                logger.info("[MEDIUM] FSM domain mismatch — silent")
                return False  # not handled, let FSM continue

        self._last_rag = result
        logger.info("FSM RAG intercept: score=%.3f article=%s", result.score, result.article.id)
        await self.egress.say(
            result.answer, self.turn, t_start,
            self.state.current_step_id if self.state else "", self.tts_chain, self.tts,
        )
        return True

    # ── Phase 3: expert handoff — delegated to call.handoff.HandoffCoordinator ─

    def start_redis_answer_subscriber(self, redis_url: str) -> asyncio.Task:
        return self.handoff.start_redis_answer_subscriber(redis_url, self.on_answer)

    # ── call termination (D1/D2 stop-the-bleeding) ─────────────────────────

    async def end_call(self, reason: str, step_id: str) -> None:
        """Send the terminal event, run the adapter's call-end side effect,
        and mark the call over."""
        payload = (
            HandoffPayload(step_id=step_id).to_dict()
            if reason == "handoff"
            else HangupPayload(step_id=step_id).to_dict()
        )
        await self.egress.send(payload)
        await self.egress.adapter.on_call_end(reason, self.ctx.session_id)
        self.call_ended.set()

    async def speak_fallback_and_end_call(
        self, message: str = _FALLBACK_ERROR_MESSAGE, reason: str = "hangup"
    ) -> None:
        """Speak a Vietnamese fallback line and end the call cleanly. Used
        when an unrecoverable error occurs mid-call so the caller never
        experiences a silent, permanently-hung connection (fixes D1/D2)."""
        if self.call_ended.is_set():
            return
        try:
            await self.egress.say(
                message, self.turn, time.perf_counter(),
                self.state.current_step_id if self.state else "", self.tts_chain, self.tts,
            )
        except Exception:
            logger.exception(
                "session_id=%s: fallback speech synthesis also failed", self.ctx.session_id
            )
        try:
            await self.end_call(reason, self.state.current_step_id if self.state else "")
        except Exception:
            logger.exception(
                "session_id=%s: failed to cleanly end call after fallback speech; "
                "forcing call_ended to avoid a silent hang",
                self.ctx.session_id,
            )
            self.call_ended.set()
