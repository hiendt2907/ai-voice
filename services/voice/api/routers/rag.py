"""RAG endpoints — embedding trigger + semantic search + gender detection."""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.config import Settings
from audio.gender import detect_gender

settings = Settings()
from rag.embedder import embed_passages, embed_query
from rag.store import fallback_text, reload_from_api, search, search_top_k, upsert_embedding

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["rag"])


class EmbedRequest(BaseModel):
    article_id: str
    texts: list[str]


class EmbedResponse(BaseModel):
    article_id: str
    dimension: int


class SearchRequest(BaseModel):
    query: str
    gender: Literal["male", "female", "unknown"] = "unknown"


class SearchResponse(BaseModel):
    matched: bool
    answer: str
    score: float
    article_id: str | None = None
    article_title: str | None = None


class TestSearchRequest(BaseModel):
    query: str
    limit: int = 3


class TestSearchResult(BaseModel):
    score: float
    article_id: str
    title: str
    answer_female: str
    answer_male: str
    answer_unknown: str
    tags: list[str]


class GenderRequest(BaseModel):
    pcm_hex: str  # hex-encoded PCM bytes
    sample_rate: int = 16000


class GenderResponse(BaseModel):
    gender: Literal["male", "female", "unknown"]


class ReloadResponse(BaseModel):
    count: int


@router.post("/embed", response_model=EmbedResponse)
async def embed_article(req: EmbedRequest) -> EmbedResponse:
    """Embed article question_variants and persist back to API."""
    if not req.texts:
        raise HTTPException(status_code=400, detail="texts must not be empty")

    vecs = embed_passages(req.texts)
    # Mean pool across variants
    import numpy as np  # noqa: PLC0415

    mean_vec = np.mean(vecs, axis=0).tolist()
    embedding_json = json.dumps(mean_vec)

    # Persist to NestJS API via internal endpoint (no auth required)
    internal_url = settings.api_url.replace("/api/v1", "")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.patch(
                f"{internal_url}/api/v1/internal/knowledge/{req.article_id}/embedding",
                json={"embeddingJson": embedding_json},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to persist embedding for %s: %s", req.article_id, exc)

    # Update in-memory store immediately
    upsert_embedding(req.article_id, mean_vec)

    return EmbedResponse(article_id=req.article_id, dimension=len(mean_vec))


@router.post("/search", response_model=SearchResponse)
def rag_search(req: SearchRequest) -> SearchResponse:
    """Semantic search against KB. Returns matched answer or fallback message."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    query_vec = embed_query(req.query)
    result = search(query_vec, gender=req.gender, max_threshold=settings.rag_confidence_default)

    if result is None:
        return SearchResponse(
            matched=False,
            answer=fallback_text(req.gender),
            score=0.0,
        )

    return SearchResponse(
        matched=True,
        answer=result.answer,
        score=result.score,
        article_id=result.article.id,
        article_title=result.article.title,
    )


@router.post("/gender", response_model=GenderResponse)
def detect_gender_endpoint(req: GenderRequest) -> GenderResponse:
    """Detect caller gender from hex-encoded PCM audio bytes."""
    try:
        pcm_bytes = bytes.fromhex(req.pcm_hex)
    except ValueError:
        raise HTTPException(status_code=400, detail="pcm_hex must be valid hex")

    gender = detect_gender(pcm_bytes, req.sample_rate)
    return GenderResponse(gender=gender)


@router.post("/test-search", response_model=list[TestSearchResult])
def rag_test_search(req: TestSearchRequest) -> list[TestSearchResult]:
    """Return top-K KB articles for a query (no threshold filter). Used by Portal KB test UI."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    query_vec = embed_query(req.query)
    top = search_top_k(query_vec, k=req.limit)

    return [
        TestSearchResult(
            score=round(score, 4),
            article_id=article.id,
            title=article.title,
            answer_female=article.answer_female or article.answer_text,
            answer_male=article.answer_male or article.answer_text,
            answer_unknown=article.answer_text,
            tags=article.tags,
        )
        for article, score in top
    ]


@router.post("/reload", response_model=ReloadResponse)
async def reload_store() -> ReloadResponse:
    """Reload KB articles from API into memory."""
    count = await reload_from_api(settings.api_url)
    return ReloadResponse(count=count)
