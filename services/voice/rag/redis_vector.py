"""Redis 8 vectorset operations + semantic text cache.

Score semantics (verified experimentally with Redis 8.8.0):
    VSIM returns (1 + cosine_similarity) / 2  ∈ [0, 1]
    → cosine_similarity = 2 * vsim_score - 1
    → to_redis_threshold(t) = (1 + t) / 2

Key schema:
    ai-voice:kb:{campaign_id}             — vectorset (campaign + global articles)
    ai-voice:cache:{campaign_id}:{md5}    — text cache, TTL 24h (string JSON)
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import struct
from typing import Any

logger = logging.getLogger(__name__)

_KB_PREFIX = "ai-voice:kb"
_CACHE_PREFIX = "ai-voice:cache"


# ── Key helpers ────────────────────────────────────────────────────────────────

def kb_key(campaign_id: str) -> str:
    return f"{_KB_PREFIX}:{campaign_id}"


def _normalize_query(query: str) -> str:
    """Normalize STT output for cache key: lowercase, strip punctuation, collapse whitespace."""
    text = query.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def cache_key(campaign_id: str, query: str) -> str:
    digest = hashlib.md5(_normalize_query(query).encode()).hexdigest()
    return f"{_CACHE_PREFIX}:{campaign_id}:{digest}"


# ── Encoding ───────────────────────────────────────────────────────────────────

def to_fp32_bytes(embedding: list[float]) -> bytes:
    return struct.pack(f"{len(embedding)}f", *embedding)


def vsim_to_cosine(vsim_score: float) -> float:
    """Convert Redis VSIM score → cosine similarity. Formula: 2*s - 1."""
    return 2.0 * vsim_score - 1.0


# ── Vectorset operations ───────────────────────────────────────────────────────

async def vadd(redis: Any, campaign_id: str, article_id: str, embedding: list[float]) -> None:
    key = kb_key(campaign_id)
    blob = to_fp32_bytes(embedding)
    try:
        await redis.execute_command("VADD", key, "FP32", blob, article_id)
    except Exception as exc:
        logger.warning("VADD failed %s/%s: %s", campaign_id, article_id, exc)


async def vclear(redis: Any, campaign_id: str) -> None:
    """Delete entire vectorset for a campaign."""
    try:
        await redis.delete(kb_key(campaign_id))
    except Exception as exc:
        logger.warning("DEL vectorset failed %s: %s", campaign_id, exc)


async def vsim(
    redis: Any,
    campaign_id: str,
    query_embedding: list[float],
    count: int = 10,
) -> list[tuple[str, float]]:
    """Similarity search. Returns [(article_id, cosine_similarity), ...] desc."""
    blob = to_fp32_bytes(query_embedding)
    try:
        result = await redis.execute_command(
            "VSIM", kb_key(campaign_id), "FP32", blob, "WITHSCORES", "COUNT", count
        )
    except Exception as exc:
        logger.warning("VSIM failed %s: %s", campaign_id, exc)
        return []

    if not result:
        return []

    pairs: list[tuple[str, float]] = []
    for i in range(0, len(result), 2):
        aid = result[i].decode() if isinstance(result[i], bytes) else str(result[i])
        cosine_sim = vsim_to_cosine(float(result[i + 1]))
        pairs.append((aid, cosine_sim))
    return pairs


async def vcard(redis: Any, campaign_id: str) -> int:
    try:
        n = await redis.execute_command("VCARD", kb_key(campaign_id))
        return int(n) if n is not None else 0
    except Exception:
        return 0


# ── Text cache ─────────────────────────────────────────────────────────────────

async def cache_get(redis: Any, campaign_id: str, query: str) -> dict | None:
    key = cache_key(campaign_id, query)
    try:
        raw = await redis.get(key)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Cache GET failed: %s", exc)
    return None


async def cache_set(
    redis: Any,
    campaign_id: str,
    query: str,
    value: dict,
    ttl_s: int = 86400,
) -> None:
    key = cache_key(campaign_id, query)
    try:
        await redis.set(key, json.dumps(value), ex=ttl_s)
    except Exception as exc:
        logger.warning("Cache SET failed: %s", exc)
