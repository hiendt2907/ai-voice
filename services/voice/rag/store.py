"""KB article store backed by Redis 8 vectorset + in-memory fallback.

Startup flow:
    init(redis) → called by main.py with app.state.redis
    reload_from_api() → fetches articles → builds _article_map + _store
                      → if redis: VCLEAR + VADD per campaign vectorset

Search flow (redis mode):
    cache_lookup(query_text, campaign_id) → hit: return immediately (skip embed)
    search(query_emb, ...) → VSIM → article_ids → _article_map lookup
                           → tag + threshold filter → cache_set → return

Search flow (fallback mode, redis=None):
    search(query_emb, ...) → in-memory O(n) cosine on _store
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from rag.embedder import cosine_similarity
from rag import redis_vector

logger = logging.getLogger(__name__)

# ── Module-level state ─────────────────────────────────────────────────────────

_redis: Any = None
_article_map: dict[str, "Article"] = {}
_store: list["Article"] = []          # in-memory fallback (tests + redis=None)
_store_lock = asyncio.Lock()

FALLBACK_MALE = "Câu hỏi này để em hỏi thêm các bác sĩ chuyên môn, anh nhé. Khi có thông tin em sẽ phản hồi lại anh ngay."
FALLBACK_FEMALE = "Câu hỏi này để em hỏi thêm các bác sĩ chuyên môn, chị nhé. Khi có thông tin em sẽ phản hồi lại chị ngay."


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Article:
    id: str
    title: str
    answer_text: str
    answer_male: str | None
    answer_female: str | None
    confidence_threshold: float
    embedding: list[float] | None
    category: str | None
    tags: list[str] = dataclasses.field(default_factory=list)
    campaign_id: str | None = None


@dataclass
class SearchResult:
    article: Article
    score: float
    answer: str


# ── Initialisation ─────────────────────────────────────────────────────────────

def init(redis: Any) -> None:
    """Set the Redis client. Called once from main.py lifespan."""
    global _redis
    _redis = redis
    if redis is not None:
        logger.info("RAG store: Redis vectorset mode enabled")
    else:
        logger.info("RAG store: in-memory fallback mode (no Redis)")


# ── Reload ─────────────────────────────────────────────────────────────────────

async def reload_from_api(api_url: str, campaign_id: str | None = None) -> int:
    """Fetch active articles from NestJS, rebuild store and Redis vectorsets."""
    params = {"campaignId": campaign_id} if campaign_id else {}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{api_url}/internal/knowledge/rag-export", params=params)
        resp.raise_for_status()
        raw: list[dict] = resp.json()

    articles: list[Article] = []
    for item in raw:
        embedding: list[float] | None = None
        if item.get("embeddingJson"):
            try:
                embedding = json.loads(item["embeddingJson"])
            except (ValueError, TypeError):
                pass
        raw_tags = item.get("tags") or []
        tags: list[str] = raw_tags if isinstance(raw_tags, list) else []
        articles.append(Article(
            id=item["id"],
            title=item.get("title", ""),
            answer_text=item.get("answerText", ""),
            answer_male=item.get("answerMale"),
            answer_female=item.get("answerFemale"),
            confidence_threshold=float(item.get("confidenceThreshold", 0.82)),
            embedding=embedding,
            category=item.get("category"),
            tags=tags,
            campaign_id=item.get("scriptId") or None,
        ))

    async with _store_lock:
        _store.clear()
        _store.extend(articles)
        _article_map.clear()
        for a in articles:
            _article_map[a.id] = a

    embedded = sum(1 for a in articles if a.embedding is not None)
    logger.info("KB store reloaded: %d articles (%d embedded)", len(articles), embedded)

    if _redis is not None:
        await _index_into_redis(articles)

    return len(articles)


async def _index_into_redis(articles: list[Article]) -> None:
    """Rebuild Redis vectorsets from article list."""
    global_articles = [a for a in articles if a.campaign_id is None and a.embedding]
    campaigns = {a.campaign_id for a in articles if a.campaign_id is not None}

    indexed = 0
    for cid in campaigns:
        await redis_vector.vclear(_redis, cid)
        campaign_articles = [a for a in articles if a.campaign_id == cid and a.embedding]
        for article in campaign_articles + global_articles:
            await redis_vector.vadd(_redis, cid, article.id, article.embedding)  # type: ignore[arg-type]
            indexed += 1

    if global_articles and not campaigns:
        # Only global articles — index under "global" key
        await redis_vector.vclear(_redis, "global")
        for article in global_articles:
            await redis_vector.vadd(_redis, "global", article.id, article.embedding)  # type: ignore[arg-type]
            indexed += 1

    logger.info("Redis vectorsets rebuilt: %d vectors across %d campaigns", indexed, len(campaigns))


# ── Text cache lookup (call BEFORE embed_query to skip embedding on hit) ────────

async def cache_lookup(
    query_text: str,
    campaign_id: str,
    gender: Literal["male", "female", "unknown"] = "unknown",
) -> SearchResult | None:
    """Check text cache. Returns SearchResult if hit, None on miss."""
    if _redis is None or not campaign_id:
        return None
    cached = await redis_vector.cache_get(_redis, campaign_id, query_text)
    if not cached:
        return None
    article = _article_map.get(cached.get("article_id", ""))
    if article is None:
        return None
    answer = _resolve_answer(article, gender)
    logger.info("RAG cache hit: article=%s score=%.3f", article.id, cached.get("score", 0))
    return SearchResult(article=article, score=cached["score"], answer=answer)


# ── Search ─────────────────────────────────────────────────────────────────────

async def search(
    query_embedding: list[float],
    gender: Literal["male", "female", "unknown"] = "unknown",
    linked_kb_tags: list[str] | None = None,
    top_k: int = 1,
    max_threshold: float = 0.82,
    campaign_id: str | None = None,
    query_text: str = "",
) -> SearchResult | None:
    """Search for best matching article. Returns None if below threshold.

    When redis is available: uses VSIM then caches the result.
    When redis is None: falls back to in-memory cosine search.
    """
    if _redis is not None and campaign_id:
        result = await _search_redis(
            query_embedding, gender, linked_kb_tags, max_threshold, campaign_id
        )
        if result is not None and query_text and campaign_id:
            await redis_vector.cache_set(
                _redis, campaign_id, query_text,
                {"article_id": result.article.id, "score": result.score},
            )
        return result

    return _search_inmemory(query_embedding, gender, linked_kb_tags, top_k, max_threshold, campaign_id)


async def _search_redis(
    query_embedding: list[float],
    gender: Literal["male", "female", "unknown"],
    linked_kb_tags: list[str] | None,
    max_threshold: float,
    campaign_id: str,
) -> SearchResult | None:
    pairs = await redis_vector.vsim(_redis, campaign_id, query_embedding, count=20)
    if not pairs:
        # Try global fallback
        pairs = await redis_vector.vsim(_redis, "global", query_embedding, count=20)

    for article_id, cosine_sim in pairs:
        article = _article_map.get(article_id)
        if article is None:
            continue
        if not _tag_matches(article, linked_kb_tags):
            continue
        effective_threshold = min(article.confidence_threshold, max_threshold)
        if cosine_sim < effective_threshold:
            break  # pairs are sorted desc, no point continuing
        answer = _resolve_answer(article, gender)
        return SearchResult(article=article, score=cosine_sim, answer=answer)
    return None


def _search_inmemory(
    query_embedding: list[float],
    gender: Literal["male", "female", "unknown"],
    linked_kb_tags: list[str] | None,
    top_k: int,
    max_threshold: float,
    campaign_id: str | None,
) -> SearchResult | None:
    candidates = [
        (a, cosine_similarity(query_embedding, a.embedding))
        for a in _store
        if a.embedding and _tag_matches(a, linked_kb_tags) and _campaign_matches(a, campaign_id)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1], reverse=True)
    best_article, best_score = candidates[0]
    effective_threshold = min(best_article.confidence_threshold, max_threshold)
    if best_score < effective_threshold:
        return None
    return SearchResult(article=best_article, score=best_score, answer=_resolve_answer(best_article, gender))


# ── search_top_k (Portal KB test UI) ──────────────────────────────────────────

def search_top_k(
    query_embedding: list[float],
    k: int = 3,
) -> list[tuple["Article", float]]:
    """Return top-k by cosine similarity, no threshold (used by Portal test UI)."""
    candidates = [
        (a, cosine_similarity(query_embedding, a.embedding))
        for a in _store
        if a.embedding
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:k]


# ── Upsert after embed ─────────────────────────────────────────────────────────

def upsert_embedding(article_id: str, embedding: list[float]) -> None:
    """Update embedding for an article in store + schedule Redis VADD."""
    for i, article in enumerate(_store):
        if article.id == article_id:
            updated = dataclasses.replace(article, embedding=embedding)
            _store[i] = updated
            _article_map[article_id] = updated
            if _redis is not None and updated.campaign_id:
                asyncio.create_task(
                    redis_vector.vadd(_redis, updated.campaign_id, article_id, embedding)
                )
            return


# ── Helpers ────────────────────────────────────────────────────────────────────

def fallback_text(gender: Literal["male", "female", "unknown"]) -> str:
    return FALLBACK_MALE if gender != "female" else FALLBACK_FEMALE


def _resolve_answer(
    article: Article,
    gender: Literal["male", "female", "unknown"],
) -> str:
    if gender == "male" and article.answer_male:
        return article.answer_male
    if gender == "female" and article.answer_female:
        return article.answer_female
    return article.answer_text


def _tag_matches(article: Article, linked_kb_tags: list[str] | None) -> bool:
    if not linked_kb_tags:
        return True
    if article.category and article.category in linked_kb_tags:
        return True
    return bool(set(article.tags) & set(linked_kb_tags))


def _campaign_matches(article: Article, campaign_id: str | None) -> bool:
    if campaign_id is None:
        return True
    return article.campaign_id is None or article.campaign_id == campaign_id
