"""DialogueEngine — the LLM/Conversation path: RAG search + grounding,
ConversationEngine prompt assembly/history, and LLM-token-stream-to-TTS.

Used by two callers:
  - `execution_mode: "rag_assisted"` scripts drive every turn through
    `handle_turn()` (was `_rag_turn` in ws.py).
  - FSM-mode scripts use `rag_lookup()` for mid-conversation question
    interception (`call/turn.py`'s `_fsm_rag_intercept`), sharing the same
    embed/cache-lookup/search primitive so the two paths don't duplicate it.

FSM (`runtime/fsm.py`, `runtime/executor.py`) is explicitly NOT part of this
module — see `call/turn.py` for where the two are switched between.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any

from call.egress import EgressSender
from call.events import BeatPayload, CallContext
from llm.conversation import REFUSAL_SENTINEL, ConversationEngine
from llm.sentence_splitter import SentenceSplitter
from runtime.guardrails import is_blacklisted
from tts.chain import TTSChain
from tts.fillers import FillerSelector
from tts.params import EmotionState

if TYPE_CHECKING:
    from runtime.session import SessionState

logger = logging.getLogger(__name__)


class DialogueEngine:
    def __init__(
        self,
        egress: EgressSender,
        ctx: CallContext,
        *,
        conv_engine: ConversationEngine | None,
        tts_chain: TTSChain | None,
        tts: object | None,
        filler_selector: FillerSelector,
        kb_grounding_enabled: bool,
        max_history_turns: int,
        sentence_split_min_chars: int,
        rag_confidence_default: float,
        rag_context_floor: float = 0.45,
        on_tts_start: Callable[[], None] = lambda: None,
        on_tts_end: Callable[[], None] = lambda: None,
    ) -> None:
        self.egress = egress
        self.ctx = ctx
        self.conv_engine = conv_engine
        self.tts_chain = tts_chain
        self.tts = tts
        self.filler_selector = filler_selector
        self.kb_grounding_enabled = kb_grounding_enabled
        self.max_history_turns = max_history_turns
        self.sentence_split_min_chars = sentence_split_min_chars
        self.rag_confidence_default = rag_confidence_default
        self.rag_context_floor = rag_context_floor
        self.on_tts_start = on_tts_start
        self.on_tts_end = on_tts_end

    # ── shared RAG primitive ──────────────────────────────────────────────

    async def rag_lookup(self, utterance: str, gender: str) -> Any | None:
        """Text-cache lookup, falling back to embed + vector search. Shared
        by `handle_turn` (rag_assisted mode) and FSM mid-turn interception."""
        from rag import store as rag_store  # noqa: PLC0415

        linked_tags: list[str] = self.ctx.script.get("linkedKbTags", [])
        try:
            result = await rag_store.cache_lookup(utterance, self.ctx.campaign_id or "", gender)
            if result is None:
                from rag.embedder import embed_query  # noqa: PLC0415

                loop = asyncio.get_running_loop()
                query_emb = await loop.run_in_executor(None, embed_query, utterance)
                result = await rag_store.search(
                    query_emb,
                    gender=gender,
                    linked_kb_tags=linked_tags or None,
                    max_threshold=self.rag_confidence_default,
                    campaign_id=self.ctx.campaign_id,
                    query_text=utterance,
                )
            return result
        except Exception as exc:
            logger.warning("RAG search error: %s", exc)
            return None

    def get_history(self, state: SessionState | None) -> list[tuple[str, str]]:
        """Extract last N (user, agent) turn pairs from transcript."""
        if state is None:
            return []
        entries = list(state.transcript)
        pairs: list[tuple[str, str]] = []
        i = 0
        while i < len(entries) - 1:
            if entries[i].role == "user" and entries[i + 1].role == "agent":
                pairs.append((entries[i].text, entries[i + 1].text))
                i += 2
            else:
                i += 1
        return pairs[-self.max_history_turns:]

    # ── rag_assisted mode: full turn handling ─────────────────────────────

    async def handle_turn(
        self,
        utterance: str,
        turn: int,
        t_start: float,
        state: SessionState | None,
        tts_interrupt: asyncio.Event,
        escalate: Any,
    ) -> None:
        """Handle one turn for `execution_mode: rag_assisted` scripts.

        `escalate` is an async callable(utterance) — Phase 3 handoff — kept
        as an injected callback so this module doesn't depend on `call.turn`.
        """
        current_emotion = EmotionState(state.current_emotion() if state else "neutral")

        filler_text, filler_pcm = self.filler_selector.next_audio_for_emotion(current_emotion.label)
        filler_task = asyncio.create_task(
            self.egress.emit_filler(
                filler_text, filler_pcm, turn, t_start,
                state.current_step_id if state else "", self.tts_chain, self.tts,
            )
        )

        gender = state.slots.get("gender", "unknown") if state else "unknown"  # type: ignore[union-attr]
        result = await self.rag_lookup(utterance, gender)

        await filler_task  # ensure filler finishes before real response

        if result is not None:
            self.ctx.last_rag_score = result.score

            if self.ctx.interception_mode == "shadow":
                logger.info("[SHADOW] would-say: %.80s (score=%.3f)", result.answer, result.score)
                return

            if self.ctx.interception_mode == "medium" and self.ctx.interception_domains:
                article_tags = set(result.article.tags or [])
                if result.article.category:
                    article_tags.add(result.article.category)
                if not article_tags & set(self.ctx.interception_domains):
                    logger.info("[MEDIUM] domain mismatch — silent (article=%s)", result.article.id)
                    return

            logger.info("RAG hit: score=%.3f article=%s", result.score, result.article.id)
            if self.conv_engine is not None and self.kb_grounding_enabled:
                gen = self.conv_engine.stream_response(
                    utterance=utterance,
                    kb_context=result.answer,
                    history=self.get_history(state),
                    emotion=current_emotion,
                )
                await self._tts_stream(gen, turn, t_start, current_emotion, tts_interrupt, state)
            else:
                await self.egress.say(
                    result.answer, turn, t_start,
                    state.current_step_id if state else "", self.tts_chain, self.tts,
                )
        else:
            from rag import store as rag_store  # noqa: PLC0415

            self.ctx.last_rag_score = 0.0
            if self.ctx.interception_mode == "shadow":
                logger.info("[SHADOW] fallback (no RAG match)")
                return

            fallback_gender = gender if gender in ("male", "female") else "unknown"
            blacklisted = is_blacklisted(utterance)

            reasoned = False
            if self.conv_engine is not None and not blacklisted:
                context = await self._loose_rag_context(utterance, gender)
                if context is not None:
                    reasoned = await self._reason_and_speak(
                        utterance, context, turn, t_start, current_emotion,
                        tts_interrupt, state, escalate,
                    )

            if not reasoned:
                # Diagnosis/prescription/prognosis questions get an explicit
                # doctor-callback promise instead of the generic "em sẽ hỏi
                # thêm" RAG-miss line — the caller asked something the AI
                # must never answer itself, not something it merely doesn't
                # know yet. The call keeps listening for the next utterance
                # either way (turn_handler loops back), so this line also
                # explicitly invites the caller to continue with anything
                # else instead of leaving the call hanging on the refusal.
                if blacklisted:
                    fallback_msg = rag_store.diagnosis_escalation_text(fallback_gender)
                else:
                    fallback_msg = self.ctx.script.get(
                        "ragFallbackMessage", rag_store.fallback_text(fallback_gender)
                    )
                await self.egress.say(
                    fallback_msg, turn, t_start,
                    state.current_step_id if state else "", self.tts_chain, self.tts,
                )
                if state:
                    await escalate(utterance)

    # ── Tầng 3: LLM reasoning when RAG has no confirmed answer ─────────────
    #
    # Three-layer gate, only the third one touches an LLM:
    #   1. is_blacklisted() — deterministic regex, evaluated above, before
    #      this is even called. Diagnosis/prescription/pricing questions
    #      never reach the model, so a prompt-injected "ignore your rules"
    #      can't bypass it the way a system-prompt-only rule could.
    #   2. _loose_rag_context() — rag_context_floor gate below. No KB
    #      article is even loosely relevant → nothing to ground the model
    #      on, so don't call it (ungrounded generation is exactly what we're
    #      trying to avoid).
    #   3. The model itself, forced by ConversationEngine's system prompt to
    #      answer only from the given context or emit REFUSAL_SENTINEL
    #      verbatim — detected here by prefix match on the streamed output.

    async def _loose_rag_context(self, utterance: str, gender: str) -> str | None:
        """Same search primitive as rag_lookup(), but at rag_context_floor
        instead of rag_confidence_default — loose enough to hand the LLM
        something to ground on, without being confident enough to speak
        directly as a KB answer. query_text is deliberately omitted so this
        never populates the semantic cache that rag_lookup()'s cache_lookup()
        reads from — a floor-level match must never be replayed later as a
        confirmed direct answer."""
        from rag import store as rag_store  # noqa: PLC0415
        from rag.embedder import embed_query  # noqa: PLC0415

        linked_tags: list[str] = self.ctx.script.get("linkedKbTags", [])
        try:
            loop = asyncio.get_running_loop()
            query_emb = await loop.run_in_executor(None, embed_query, utterance)
            result = await rag_store.search(
                query_emb,
                gender=gender,  # type: ignore[arg-type]
                linked_kb_tags=linked_tags or None,
                max_threshold=self.rag_context_floor,
                campaign_id=self.ctx.campaign_id,
            )
            return result.answer if result is not None else None
        except Exception as exc:
            logger.warning("Loose RAG context lookup error: %s", exc)
            return None

    async def _reason_and_speak(
        self,
        utterance: str,
        kb_context: str,
        turn: int,
        t_start: float,
        emotion: EmotionState,
        tts_interrupt: asyncio.Event,
        state: SessionState | None,
        escalate: Any,
    ) -> bool:
        """Stream a grounded LLM answer. Returns True if something was
        actually spoken (a real answer, or the model's own refusal line) —
        the caller must not also speak the static fallback in that case."""
        accumulated: list[str] = []

        async def _tap(gen: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
            async for token in gen:
                accumulated.append(token)
                yield token

        gen = self.conv_engine.stream_response(  # type: ignore[union-attr]
            utterance=utterance,
            kb_context=kb_context,
            history=self.get_history(state),
            emotion=emotion,
        )
        await self._tts_stream(_tap(gen), turn, t_start, emotion, tts_interrupt, state)

        full_text = "".join(accumulated).strip()
        if not full_text:
            return False  # LLM call failed/empty — let caller speak the static fallback

        if full_text.startswith(REFUSAL_SENTINEL):
            logger.info("Reasoning tier: model declined (insufficient grounding)")
            if state:
                await escalate(utterance)
        else:
            logger.info("Reasoning tier answered: %.80s", full_text)
        return True

    # ── LLM token stream -> sentence splitter -> TTS ──────────────────────

    async def _tts_stream(
        self,
        sentence_gen: AsyncGenerator[str, None],
        turn: int,
        t_start: float,
        emotion: EmotionState,
        interrupt: asyncio.Event,
        state: SessionState | None,
    ) -> None:
        if self.tts_chain is None:
            # Beat-only fallback: buffer full response and send as one beat
            full_text = ""
            async for token in sentence_gen:
                full_text += token
            beat = BeatPayload(
                text=full_text, pause_ms=500, turn=turn,
                step_id=state.current_step_id if state else "",
                ttfa_ms=round((time.perf_counter() - t_start) * 1000, 1),
            )
            await self.egress.send_beat(beat)
            return

        splitter = SentenceSplitter(min_chars=self.sentence_split_min_chars)
        first_audio = True
        engine_name = self.tts_chain.primary_engine_name()
        params = emotion.to_tts_params(engine_name)

        async def _send_sentence(sentence: str) -> None:
            nonlocal first_audio
            if interrupt.is_set():
                return
            beat = BeatPayload(
                text=sentence, pause_ms=300, turn=turn,
                step_id=state.current_step_id if state else "",
                ttfa_ms=round((time.perf_counter() - t_start) * 1000, 1),
            )
            await self.egress.send_beat(beat)
            self.on_tts_start()
            try:
                gen = await self.tts_chain.stream_synthesize(sentence, params)  # type: ignore[union-attr]
                async for chunk in gen:
                    if interrupt.is_set():
                        return
                    await self.egress.send_audio(chunk, turn)
                    if first_audio:
                        logger.info("TTFA=%.0fms", (time.perf_counter() - t_start) * 1000)
                        first_audio = False
            except Exception as exc:
                logger.warning("_tts_stream synthesis error: %s", exc)
            finally:
                self.on_tts_end()

        try:
            async for token in sentence_gen:
                if interrupt.is_set():
                    break
                for sentence in splitter.feed(token):
                    await _send_sentence(sentence)
        finally:
            # A `break` above (barge-in) previously left `sentence_gen`
            # suspended mid-`yield`, so the upstream httpx stream it holds
            # open (see llm/conversation.py::stream_response) was only
            # closed whenever the generator got garbage-collected —
            # sometimes seconds later. `aclose()` closes it immediately
            # regardless of why the loop ended (interrupt or natural
            # exhaustion, where it's a no-op).
            await sentence_gen.aclose()

        if interrupt.is_set():
            return

        for sentence in splitter.flush():
            await _send_sentence(sentence)
