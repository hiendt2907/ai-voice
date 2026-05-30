"""In-memory NLU document store with cosine similarity search.

Loaded from NestJS API on startup. Stores intent examples, fillers, reprompts,
and dialog nodes — all as searchable vector documents.

Provides:
  search_intents()  — vector cosine search over intent examples
  get_fillers()     — pool of filler phrases by context type
  get_reprompts()   — reprompt variants for a given script step
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Literal

import httpx

from rag.embedder import cosine_similarity

logger = logging.getLogger(__name__)

NluDocType = Literal["intent", "filler", "reprompt", "dialog_node"]


@dataclass
class NluDoc:
    id: str
    type: NluDocType
    label: str
    content: str
    meta: dict
    embedding: list[float] | None
    campaign_id: str | None
    script_id: str | None


@dataclass
class IntentMatch:
    intent: str
    score: float
    preset_slots: dict[str, str] = field(default_factory=dict)


_store: list[NluDoc] = []
_store_lock = asyncio.Lock()


async def reload_from_api(api_url: str, campaign_id: str | None = None) -> int:
    """Fetch all active NLU documents from NestJS and rebuild in-memory store."""
    url = f"{api_url}/internal/nlu/export"
    params = {}
    if campaign_id:
        params["campaignId"] = campaign_id

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        raw: list[dict] = resp.json()

    docs: list[NluDoc] = []
    for item in raw:
        embedding: list[float] | None = None
        if item.get("embeddingJson"):
            try:
                embedding = json.loads(item["embeddingJson"])
            except (ValueError, TypeError):
                pass
        docs.append(NluDoc(
            id=item["id"],
            type=item["type"],
            label=item["label"],
            content=item["content"],
            meta=item.get("meta") or {},
            embedding=embedding,
            campaign_id=item.get("campaignId"),
            script_id=item.get("scriptId"),
        ))

    async with _store_lock:
        _store.clear()
        _store.extend(docs)

    embedded = sum(1 for d in docs if d.embedding is not None)
    by_type: dict[str, int] = {}
    for d in docs:
        by_type[d.type] = by_type.get(d.type, 0) + 1
    logger.info("NLU store reloaded: %d docs (%d embedded) — %s", len(docs), embedded, by_type)
    return len(docs)


def search_intents(
    query_embedding: list[float],
    top_k: int = 3,
    campaign_id: str | None = None,
) -> list[IntentMatch]:
    """Search intent examples by cosine similarity.

    Returns top_k matches sorted by score descending.
    Filters to global docs (campaignId=null) + campaign-specific if campaign_id given.
    """
    candidates = [
        d for d in _store
        if d.type == "intent" and d.embedding is not None
        and (campaign_id is None or d.campaign_id is None or d.campaign_id == campaign_id)
    ]

    scored = [
        (d, cosine_similarity(query_embedding, d.embedding))  # type: ignore[arg-type]
        for d in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    results: list[IntentMatch] = []
    for doc, score in scored[:top_k]:
        preset_slots: dict[str, str] = {}
        raw_slots = doc.meta.get("slots")
        if isinstance(raw_slots, dict):
            preset_slots = {k: str(v) for k, v in raw_slots.items()}
        results.append(IntentMatch(intent=doc.label, score=score, preset_slots=preset_slots))
    return results


def get_fillers(context_type: str, campaign_id: str | None = None) -> list[str]:
    """Return filler phrases for a given context type.

    Falls back to hardcoded defaults when store has no matching docs.
    """
    phrases = [
        d.content for d in _store
        if d.type == "filler" and d.label == context_type and d.embedding is not None
        and (campaign_id is None or d.campaign_id is None or d.campaign_id == campaign_id)
    ]
    if phrases:
        return phrases
    # Hardcoded fallback — store is empty or not yet loaded
    return _FILLER_FALLBACKS.get(context_type, ["Dạ,"])


def get_reprompts(step_id: str, script_id: str | None = None) -> list[str]:
    """Return reprompt variants for a script step, ordered by meta.order."""
    docs = [
        d for d in _store
        if d.type == "reprompt" and d.label == step_id
        and (script_id is None or d.script_id is None or d.script_id == script_id)
    ]
    docs.sort(key=lambda d: int(d.meta.get("order", 0)))
    return [d.content for d in docs]


def upsert_embedding(doc_id: str, embedding: list[float]) -> None:
    """Update embedding for a document already in store (called after embed)."""
    import dataclasses  # noqa: PLC0415
    for i, doc in enumerate(_store):
        if doc.id == doc_id:
            _store[i] = dataclasses.replace(doc, embedding=embedding)
            return


_FILLER_FALLBACKS: dict[str, list[str]] = {
    "thinking": ["Dạ,", "Vâng,", "À,", "Ừm,"],
    "ack": ["Dạ vâng ạ.", "Được ạ.", "Vâng ạ.", "Dạ em hiểu ạ."],
    "wait": ["Dạ, bác đợi em một chút ạ.", "Em xem ngay ạ.", "Để em kiểm tra lại ạ."],
    "checking": [
        "Dạ, để em kiểm tra lịch cho anh/chị nhé...",
        "Vâng, em xem ngay ạ...",
        "Để em kiểm tra trong hệ thống nhé...",
    ],
    "confirming": [
        "Vâng, để em xác nhận lại thông tin ạ...",
        "Để em đặt lịch cho anh/chị ạ...",
    ],
    "ack_slot": ["Vâng, {value} ạ.", "Dạ, {value} ạ.", "À, {value} ạ."],
}
