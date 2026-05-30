"""AiDrivenExecutor — handles scripts with execution_mode == "ai_driven" / "rag_assisted".

Turn flow:
1. Utterance from STT
2. Filler response immediately (Dạ, À, …) → TTS ≤50ms
3. Embed utterance → vector store search (Phase 2: replaces LLM-only path)
4. score >= threshold → TTS KB answer (gender-resolved)
5. score < threshold → Phase 3 Telegram escalation
   a. TTS: waiting_message
   b. POST to Telegram bot with callback URL
6. Barge-in: if voice detected while AI speaking → stop TTS + filler
7. Gender detect: pitch analysis to choose anh/chị
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiTurnResult:
    filler: str
    main_response: str
    escalated: bool
    session_id: str


class AiDrivenExecutor:
    """Execute a single turn for an ai_driven script body.

    Args:
        script_body: Parsed dict from the script version JSON.
        tts: TTS engine instance (must have async stream_step / synthesize).
        stt: STT engine instance (optional, for barge-in detection).
        telegram_notifier: TelegramNotifier instance (optional).

    Note:
        The LLM-free-form answer path (_rag_query via LLM chat) has been
        removed (Phase 2.1). All answers come from KB vector store or
        template fallback. LLM is only used for NLU intent classification
        in FSM scripts (llm/nlu.py).
    """

    def __init__(
        self,
        script_body: dict,
        tts=None,
        stt=None,
        telegram_notifier=None,
    ) -> None:
        self._body = script_body
        self._tts = tts
        self._stt = stt
        self._telegram = telegram_notifier
        self._is_first_turn = True

        persona = script_body.get("persona", {})
        self._fillers: list[str] = persona.get("fillers", ["Dạ"])
        self._barge_in: bool = bool(persona.get("barge_in", True))
        self._gender_detect: bool = bool(persona.get("gender_detect", True))
        self._greeting: str = script_body.get("greeting", "")
        self._fallback_msg: str = script_body.get(
            "fallback_message", "Dạ để em kiểm tra thêm thông tin ạ"
        )

        rag = script_body.get("rag", {})
        self._rag_enabled: bool = bool(rag.get("enabled", False))
        self._linked_kb_tags: list[str] = rag.get("linkedKbTags", [])

        escalation = script_body.get("escalation", {})
        self._telegram_enabled: bool = bool(escalation.get("telegram", False))
        self._waiting_msg: str = escalation.get(
            "waiting_message", "Dạ em đã chuyển câu hỏi của bác cho bác sĩ, bác chờ chút ạ"
        )

    def _pick_filler(self) -> str:
        return random.choice(self._fillers) if self._fillers else "Dạ"

    async def _rag_search(
        self,
        utterance: str,
        gender: str = "unknown",
    ) -> str | None:
        """Search KB vector store. Returns answer text or None if below threshold.

        Uses in-memory rag.store (vector embeddings loaded from NestJS API).
        No LLM generation — returns KB template text only.
        """
        if not self._rag_enabled:
            return None
        try:
            from rag import store as rag_store  # noqa: PLC0415
            from rag.embedder import embed_query  # noqa: PLC0415

            from api.config import Settings as _Settings  # noqa: PLC0415
            _cfg = _Settings()

            # Text cache check first (skip embedding on repeated queries)
            result = await rag_store.cache_lookup(utterance, "", gender)  # type: ignore[arg-type]
            if result is None:
                loop = asyncio.get_running_loop()
                query_emb = await loop.run_in_executor(None, embed_query, utterance)
                result = await rag_store.search(
                    query_emb,
                    gender=gender,  # type: ignore[arg-type]
                    linked_kb_tags=self._linked_kb_tags,
                    max_threshold=_cfg.rag_confidence_default,
                )
            if result is not None:
                logger.info(
                    "RAG hit: score=%.3f article=%s", result.score, result.article.id
                )
                return result.answer
        except Exception as exc:
            logger.warning("RAG search error: %s", exc)
        return None

    async def _send_telegram(self, utterance: str, session_id: str, callback_url: str = "") -> None:
        if not self._telegram_enabled or not self._telegram:
            return
        try:
            await self._telegram.send(utterance, session_id, callback_url)
            logger.info("Telegram escalation sent for session %s", session_id)
        except Exception as exc:
            logger.warning("Telegram escalation failed: %s", exc)

    async def process_turn(
        self,
        utterance: str,
        session_id: str = "",
        gender: str = "unknown",
        callback_url: str = "",
    ) -> AiTurnResult:
        """Process one user utterance and return the AI response.

        First turn: returns greeting.
        Subsequent turns: filler → vector RAG search → TTS template or escalation.
        """
        filler = self._pick_filler()

        if self._is_first_turn:
            self._is_first_turn = False
            return AiTurnResult(
                filler=filler,
                main_response=self._greeting,
                escalated=False,
                session_id=session_id,
            )

        # Phase 2: vector RAG search (no LLM generation)
        rag_answer = await self._rag_search(utterance, gender=gender)

        if rag_answer:
            return AiTurnResult(
                filler=filler,
                main_response=rag_answer,
                escalated=False,
                session_id=session_id,
            )

        # Phase 3: Telegram escalation when below confidence threshold
        if self._telegram_enabled:
            await self._send_telegram(utterance, session_id, callback_url)
            return AiTurnResult(
                filler=filler,
                main_response=self._waiting_msg,
                escalated=True,
                session_id=session_id,
            )

        # No RAG result and no Telegram → generic fallback
        return AiTurnResult(
            filler=filler,
            main_response=self._fallback_msg,
            escalated=False,
            session_id=session_id,
        )
