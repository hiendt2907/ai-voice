"""Phase 3 — expert handoff: escalate an unanswered question to Telegram,
time it out with a spoken follow-up, or inject the doctor's answer back into
the call. Split out of `call/turn.py` to keep that module under the 400-line
budget; owned/driven by `TurnOrchestrator` (`call/turn.py`), not standalone.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from call.egress import EgressSender
from call.events import CallContext
from runtime.session import PendingQuestion, SessionState

logger = logging.getLogger(__name__)

_VN_TZ = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh


def _after_hours_hint() -> str:
    now = datetime.now(_VN_TZ)
    if now.hour >= 22 or now.hour < 7:
        return "sáng mai"
    return "khoảng 15 phút nữa"


class _StateHolder(Protocol):
    """The subset of TurnOrchestrator this module needs — a live,
    replaceable reference to the current SessionState, current turn number,
    and the shared call-ended signal."""

    state: SessionState | None
    turn: int
    call_ended: asyncio.Event


class HandoffCoordinator:
    def __init__(
        self,
        owner: _StateHolder,
        egress: EgressSender,
        ctx: CallContext,
        *,
        tts_chain: object | None,
        tts: object | None,
        settings: Any,
    ) -> None:
        self.owner = owner
        self.egress = egress
        self.ctx = ctx
        self.tts_chain = tts_chain
        self.tts = tts
        self.settings = settings
        self.pending_question_tasks: list[asyncio.Task] = []

    async def escalate_question(self, utterance: str) -> None:
        """Send to Telegram + schedule the timeout."""
        if self.owner.state is None:
            return

        question_id = str(uuid.uuid4())
        q = PendingQuestion(
            question_id=question_id,
            question_text=utterance,
            timeout_seconds=self.settings.question_timeout_seconds,
        )
        self.owner.state = self.owner.state.with_pending_question(q)

        callback_url = (
            f"{self.settings.voice_worker_base_url}/callbacks/question"
            f"/{self.ctx.session_id}/{question_id}"
        )

        if self.settings.notify_platform == "telegram" and self.settings.telegram_bot_token:
            try:
                from notify.telegram import TelegramNotifier  # noqa: PLC0415

                notifier = TelegramNotifier(
                    bot_token=self.settings.telegram_bot_token,
                    group_id=self.settings.telegram_group_id,
                )
                await notifier.send(utterance, self.ctx.session_id, callback_url)
                await notifier.aclose()
            except Exception as exc:
                logger.warning("Telegram notify failed: %s", exc)

        task = asyncio.create_task(self._question_timeout(question_id))
        self.pending_question_tasks.append(task)

    async def _question_timeout(self, question_id: str) -> None:
        """After timeout, inject the follow-up template."""
        timeout_s = self.settings.question_timeout_seconds
        await asyncio.sleep(timeout_s)

        if self.owner.call_ended.is_set() or self.owner.state is None:
            return
        if not any(q.question_id == question_id for q in self.owner.state.pending_questions):
            return  # already answered

        self.owner.state = self.owner.state.without_pending_question(question_id)
        time_hint = _after_hours_hint()
        followup = (
            f"Dạ về câu hỏi vừa rồi, bác sĩ sẽ liên hệ lại {time_hint} ạ. "
            "Bác có cần đặt lịch khám ngay bây giờ không ạ?"
        )
        logger.info("Question %s timed out after %ds, injecting follow-up", question_id, timeout_s)
        await self.egress.say(
            followup, self.owner.turn, time.perf_counter(),
            self.owner.state.current_step_id, self.tts_chain, self.tts,
        )

    async def inject_answer(self, question_id: str, answer_text: str) -> None:
        """Inject the doctor's answer into the ongoing conversation."""
        if self.owner.state is None:
            return
        self.owner.state = self.owner.state.without_pending_question(question_id)
        full_text = f"Dạ về câu hỏi ban nãy, {answer_text}"
        logger.info("Injecting answer for question_id=%s", question_id)
        await self.egress.say(
            full_text, self.owner.turn, time.perf_counter(),
            self.owner.state.current_step_id, self.tts_chain, self.tts,
        )

    def start_redis_answer_subscriber(
        self, redis_url: str, on_answer: Any
    ) -> asyncio.Task:
        return asyncio.create_task(self._redis_answer_subscriber(redis_url, on_answer))

    async def _redis_answer_subscriber(self, redis_url: str, on_answer: Any) -> None:
        """Subscribe to Redis answer:{sessionId} for doctor replies (Phase 3.4)."""
        import redis.asyncio as aioredis  # noqa: PLC0415

        channel = f"answer:{self.ctx.session_id}"
        redis: Any = None
        try:
            redis = aioredis.from_url(redis_url, decode_responses=True)
            async with redis.pubsub() as pubsub:
                await pubsub.subscribe(channel)
                logger.info("Redis: subscribed to %s", channel)
                async for message in pubsub.listen():
                    if self.owner.call_ended.is_set():
                        break
                    if message["type"] != "message":
                        continue
                    payload: str = message["data"]
                    parts = payload.split("|", 1)
                    if len(parts) == 2:
                        qid, ans = parts
                        await on_answer(qid, ans)
                        logger.info("Answer received for question_id=%s", qid)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.warning("Redis subscriber error: %s", exc)
        finally:
            if redis is not None:
                try:
                    await redis.aclose()
                except Exception:
                    pass
