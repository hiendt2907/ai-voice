"""NLU endpoints — embed trigger + store reload."""

from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from api.config import Settings
from rag.embedder import embed_query

settings = Settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nlu", tags=["nlu"])


class EmbedNluRequest(BaseModel):
    doc_id: str
    content: str


class EmbedNluResponse(BaseModel):
    doc_id: str
    dimension: int


class ReloadResponse(BaseModel):
    count: int


@router.post("/embed", response_model=EmbedNluResponse)
async def embed_nlu_doc(req: EmbedNluRequest) -> EmbedNluResponse:
    """Embed NLU document content and persist back to API."""
    vec = embed_query(req.content)
    embedding_json = json.dumps(vec)

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.patch(
                f"{settings.api_url}/internal/nlu/{req.doc_id}/embedding",
                json={"embeddingJson": embedding_json},
            )
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to persist NLU embedding for %s: %s", req.doc_id, exc)

    from nlu.store import upsert_embedding  # noqa: PLC0415
    upsert_embedding(req.doc_id, vec)

    return EmbedNluResponse(doc_id=req.doc_id, dimension=len(vec))


@router.post("/reload", response_model=ReloadResponse)
async def reload_nlu_store() -> ReloadResponse:
    """Reload NLU documents from API into memory."""
    from nlu.store import reload_from_api  # noqa: PLC0415
    count = await reload_from_api(settings.api_url)
    return ReloadResponse(count=count)
