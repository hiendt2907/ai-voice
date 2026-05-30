"""Callback endpoint — receives answers from Teams/Telegram webhook relay.

Flow:
  Teams/Telegram button click → NestJS /internal/question-answered → this endpoint
  This endpoint publishes answer to Redis pub/sub channel listened by the active WS session.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from api.config import Settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/callbacks", tags=["callbacks"])

_settings = Settings()


class QuestionAnswerDto(BaseModel):
    answer: str


async def _get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    client: aioredis.Redis = aioredis.from_url(_settings.redis_url, decode_responses=True)  # type: ignore[type-arg]
    return client


@router.post("/question/{session_id}/{question_id}")
async def receive_answer(
    session_id: str,
    question_id: str,
    dto: QuestionAnswerDto = Body(...),
) -> dict:
    """Receive an answer from the chat platform and inject it into the live WS session."""
    channel = f"answer:{session_id}"
    payload = f"{question_id}|{dto.answer}"

    try:
        redis = await _get_redis()
        subscribers = await redis.publish(channel, payload)
        logger.info(
            "Answer published: session=%s question=%s subscribers=%d",
            session_id, question_id, subscribers,
        )
        await redis.aclose()
    except Exception as exc:
        logger.error("Redis publish failed: %s", exc)
        raise HTTPException(status_code=503, detail="Failed to relay answer") from exc

    return {"ok": True, "session_id": session_id, "question_id": question_id}
