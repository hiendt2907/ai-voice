"""In-memory KB article store with cosine similarity search.

Articles are fetched from NestJS API on startup and refreshed via
reload_from_api(). Each article's embedding is the mean of its
question_variants embeddings (or None if not yet embedded).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from rag.embedder import cosine_similarity

logger = logging.getLogger(__name__)


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
    campaign_id: str | None = None  # maps to KnowledgeArticle.scriptId (campaign UUID)


@dataclass
class SearchResult:
    article: Article
    score: float
    answer: str  # gender-resolved answer text


_store: list[Article] = []
_store_lock = asyncio.Lock()

FALLBACK_MALE = "Câu hỏi này để em hỏi thêm các bác sĩ chuyên môn, anh nhé. Khi có thông tin em sẽ phản hồi lại anh ngay."
FALLBACK_FEMALE = "Câu hỏi này để em hỏi thêm các bác sĩ chuyên môn, chị nhé. Khi có thông tin em sẽ phản hồi lại chị ngay."


async def reload_from_api(api_url: str, campaign_id: str | None = None) -> int:
    """Fetch active articles from NestJS and rebuild in-memory store.

    When campaign_id is given, scopes the export to that campaign so a call only
    loads its own KB (prevents cross-campaign leakage). Omitting it loads all
    active articles (used by the global startup warm-up).
    """
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
        articles.append(
            Article(
                id=item["id"],
                title=item.get("title", ""),
                answer_text=item.get("answerText", ""),
                answer_male=item.get("answerMale"),
                answer_female=item.get("answerFemale"),
                confidence_threshold=float(item.get("confidenceThreshold", 0.82)),
                embedding=embedding,
                category=item.get("category"),
                tags=tags,
                campaign_id=item.get("scriptId") or None,  # scriptId stores the campaign UUID
            )
        )

    async with _store_lock:
        _store.clear()
        _store.extend(articles)

    embedded = sum(1 for a in articles if a.embedding is not None)
    logger.info("KB store reloaded: %d articles (%d embedded)", len(articles), embedded)
    return len(articles)


def search(
    query_embedding: list[float],
    gender: Literal["male", "female", "unknown"] = "unknown",
    linked_kb_tags: list[str] | None = None,
    top_k: int = 1,
    max_threshold: float = 0.82,
    campaign_id: str | None = None,
) -> SearchResult | None:
    """Search store for best matching article. Returns None if below threshold.

    Args:
        linked_kb_tags: If provided, only articles whose category or tags overlap
                        with this list are considered (Phase 2.8 metadata filter).
        max_threshold: Global cap on confidence threshold. The effective threshold
                       used is min(article.confidence_threshold, max_threshold).
                       Set this to the calibrated value for your embedding model
                       (e.g. 0.65 for MiniLM-L12 dim=384).
        campaign_id: When provided, only articles belonging to this campaign
                     (campaign_id is None meaning global) are considered.
                     Prevents cross-campaign KB leakage when the global store
                     is shared across all sessions.
    """
    def _tag_matches(article: Article) -> bool:
        if not linked_kb_tags:
            return True
        if article.category and article.category in linked_kb_tags:
            return True
        return bool(set(article.tags) & set(linked_kb_tags))

    def _campaign_matches(article: Article) -> bool:
        if campaign_id is None:
            return True
        # Allow articles scoped to this campaign OR global articles (campaign_id=None)
        return article.campaign_id is None or article.campaign_id == campaign_id

    candidates = [
        (a, cosine_similarity(query_embedding, a.embedding))
        for a in _store
        if a.embedding and _tag_matches(a) and _campaign_matches(a)
    ]

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_article, best_score = candidates[0]

    # Use the lower of per-article threshold or global cap
    effective_threshold = min(best_article.confidence_threshold, max_threshold)
    if best_score < effective_threshold:
        return None

    answer = _resolve_answer(best_article, gender)
    return SearchResult(article=best_article, score=best_score, answer=answer)


def search_top_k(
    query_embedding: list[float],
    k: int = 3,
) -> list[tuple["Article", float]]:
    """Return top-k articles sorted by cosine similarity (no threshold filtering).

    Used by the KB test interface so QA can see all results regardless of threshold.
    """
    candidates = [
        (a, cosine_similarity(query_embedding, a.embedding))
        for a in _store
        if a.embedding
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:k]


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


def upsert_embedding(article_id: str, embedding: list[float]) -> None:
    """Update embedding for an article already in the store (called after embed)."""
    for article in _store:
        if article.id == article_id:
            idx = _store.index(article)
            _store[idx] = dataclasses.replace(article, embedding=embedding)
            return
