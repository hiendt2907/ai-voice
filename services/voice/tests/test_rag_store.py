"""Tests for RAG store — cosine search and gender resolution.

search() is async; tests use asyncio_mode=auto (configured in pyproject.toml).
The in-memory fallback path (redis=None) is tested here — no Redis required.
"""

from __future__ import annotations

import dataclasses
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.store import (
    Article,
    SearchResult,
    _resolve_answer,
    fallback_text,
    search,
    upsert_embedding,
)
import rag.store as store_module


@pytest.fixture(autouse=True)
def clear_store():
    """Reset in-memory store before each test, ensure redis=None (fallback mode)."""
    store_module._store.clear()
    store_module._article_map.clear()
    store_module._redis = None
    yield
    store_module._store.clear()
    store_module._article_map.clear()
    store_module._redis = None


def _article(
    id: str = "a1",
    embedding: list[float] | None = None,
    threshold: float = 0.82,
    answer_text: str = "Đây là câu trả lời.",
    answer_male: str | None = "Đây là câu trả lời, anh.",
    answer_female: str | None = "Đây là câu trả lời, chị.",
    tags: list[str] | None = None,
    campaign_id: str | None = None,
) -> Article:
    return Article(
        id=id,
        title="Test",
        answer_text=answer_text,
        answer_male=answer_male,
        answer_female=answer_female,
        confidence_threshold=threshold,
        embedding=embedding,
        category=None,
        tags=tags or [],
        campaign_id=campaign_id,
    )


def _unit_vec(dim: int = 4, pos: int = 0) -> list[float]:
    v = [0.0] * dim
    v[pos] = 1.0
    return v


# ── search ────────────────────────────────────────────────────────────────────

async def test_search_returns_none_when_store_empty():
    result = await search(_unit_vec(pos=0))
    assert result is None


async def test_search_returns_none_when_no_embeddings():
    store_module._store.append(_article(embedding=None))
    result = await search(_unit_vec(pos=0))
    assert result is None


async def test_search_returns_match_above_threshold():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8))
    result = await search(vec, gender="male", max_threshold=0.8, linked_kb_tags=["*"])
    assert result is not None
    assert result.score > 0.99
    assert result.answer == "Đây là câu trả lời, anh."


async def test_search_returns_none_below_threshold():
    query = _unit_vec(4, pos=0)
    different = _unit_vec(4, pos=1)
    store_module._store.append(_article(embedding=different, threshold=0.82))
    result = await search(query, max_threshold=0.82)
    assert result is None


async def test_search_max_threshold_overrides_article_threshold():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.82))
    result = await search(vec, max_threshold=0.65, linked_kb_tags=["*"])
    assert result is not None
    result2 = await search(vec, max_threshold=0.82, linked_kb_tags=["*"])
    assert result2 is not None


async def test_search_picks_best_of_multiple():
    close = [0.99, 0.01, 0.0, 0.0]
    far = [0.0, 0.0, 1.0, 0.0]
    store_module._store.append(_article(id="a1", embedding=close, threshold=0.8))
    store_module._store.append(_article(id="a2", embedding=far, threshold=0.8))
    query = _unit_vec(4, pos=0)
    result = await search(query, linked_kb_tags=["*"])
    assert result is not None
    assert result.article.id == "a1"


# ── gender resolution ─────────────────────────────────────────────────────────

def test_resolve_answer_male():
    a = _article(answer_male="anh version", answer_female="chị version")
    assert _resolve_answer(a, "male") == "anh version"


def test_resolve_answer_female():
    a = _article(answer_male="anh version", answer_female="chị version")
    assert _resolve_answer(a, "female") == "chị version"


def test_resolve_answer_unknown_uses_default():
    a = _article(answer_text="default", answer_male="anh", answer_female="chị")
    assert _resolve_answer(a, "unknown") == "default"


def test_resolve_answer_falls_back_to_default_when_override_missing():
    a = _article(answer_text="default only", answer_male=None, answer_female=None)
    assert _resolve_answer(a, "male") == "default only"
    assert _resolve_answer(a, "female") == "default only"


# ── fallback_text ─────────────────────────────────────────────────────────────

def test_fallback_text_female():
    assert "chị" in fallback_text("female")


def test_fallback_text_male():
    assert "anh" in fallback_text("male")


def test_fallback_text_unknown_defaults_to_male():
    assert "anh" in fallback_text("unknown")


# ── upsert_embedding ─────────────────────────────────────────────────────────

def test_upsert_updates_existing_article():
    art = _article(id="x", embedding=None)
    store_module._store.append(art)
    store_module._article_map["x"] = art
    new_vec = [0.1, 0.2, 0.3]
    upsert_embedding("x", new_vec)
    assert store_module._store[0].embedding == new_vec


def test_upsert_noop_for_unknown_id():
    art = _article(id="known", embedding=[1.0])
    store_module._store.append(art)
    store_module._article_map["known"] = art
    upsert_embedding("unknown", [0.5])
    assert store_module._store[0].embedding == [1.0]


# ── reload_from_api ───────────────────────────────────────────────────────────

async def test_reload_from_api_parses_articles():
    raw = [
        {
            "id": "id1",
            "title": "Giờ khám",
            "answerText": "Mở cửa 8 giờ sáng",
            "answerMale": "Mở cửa 8 giờ sáng, anh.",
            "answerFemale": "Mở cửa 8 giờ sáng, chị.",
            "embeddingJson": json.dumps([0.1, 0.2]),
            "confidenceThreshold": 0.85,
            "category": "schedule",
            "tags": ["schedule", "booking"],
            "scriptId": "camp-uuid-1234",
        }
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=raw)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("rag.store.httpx.AsyncClient", return_value=mock_client):
        count = await store_module.reload_from_api("http://api")

    assert count == 1
    assert store_module._store[0].id == "id1"
    assert store_module._store[0].embedding == [0.1, 0.2]
    assert store_module._store[0].confidence_threshold == 0.85
    assert store_module._store[0].tags == ["schedule", "booking"]
    assert store_module._store[0].campaign_id == "camp-uuid-1234"


# ── linkedKbTags filter ───────────────────────────────────────────────────────

async def test_search_tag_filter_matches_overlap():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["booking", "pricing"]))
    result = await search(vec, linked_kb_tags=["pricing"])
    assert result is not None


async def test_search_tag_filter_excludes_no_overlap():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["booking"]))
    result = await search(vec, linked_kb_tags=["lab_results"])
    assert result is None


async def test_search_tag_filter_empty_filter_matches_nothing():
    """Strict opt-in: a script that hasn't declared any linkedKbTags gets no
    KB access at all — silently matching everything let any untagged script
    see every campaign's KB content (found via real-call testing)."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["booking"]))
    result = await search(vec, linked_kb_tags=[])
    assert result is None


async def test_search_tag_filter_none_matches_nothing():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["anything"]))
    result = await search(vec, linked_kb_tags=None)
    assert result is None


async def test_search_tag_filter_wildcard_matches_all():
    """The explicit "*" tag is how a genuine catch-all (Global) campaign
    opts into seeing every article, instead of relying on the old
    empty-list-means-everything default."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["anything"]))
    result = await search(vec, linked_kb_tags=["*"])
    assert result is not None


async def test_search_tag_filter_prefers_tagged_over_untagged():
    vec = _unit_vec(4, pos=0)
    store_module._store.append(_article(id="tagged", embedding=vec, threshold=0.8, tags=["booking"]))
    store_module._store.append(_article(id="untagged", embedding=vec, threshold=0.8, tags=["other"]))
    result = await search(vec, linked_kb_tags=["booking"])
    assert result is not None
    assert result.article.id == "tagged"


# ── category matching ─────────────────────────────────────────────────────────

async def test_search_matches_article_by_category_name():
    vec = _unit_vec(pos=0)
    article = Article(
        id="a1", title="T", answer_text="A",
        answer_male=None, answer_female=None,
        confidence_threshold=0.8, embedding=vec,
        category="booking", tags=["some_other_tag"],
    )
    store_module._store.append(article)
    result = await search(vec, linked_kb_tags=["booking"])
    assert result is not None
    assert result.article.id == "a1"


async def test_search_excludes_article_when_category_not_in_filter():
    vec = _unit_vec(pos=0)
    article = Article(
        id="a1", title="T", answer_text="A",
        answer_male=None, answer_female=None,
        confidence_threshold=0.8, embedding=vec,
        category="schedule", tags=["lịch"],
    )
    store_module._store.append(article)
    result = await search(vec, linked_kb_tags=["booking"])
    assert result is None


async def test_search_category_and_tag_filter_union():
    vec = _unit_vec(pos=0)
    store_module._store.append(Article(
        id="sched", title="T", answer_text="A",
        answer_male=None, answer_female=None,
        confidence_threshold=0.8, embedding=vec,
        category="schedule", tags=["lịch"],
    ))
    store_module._store.append(Article(
        id="price", title="T", answer_text="A",
        answer_male=None, answer_female=None,
        confidence_threshold=0.8, embedding=[0.0, 1.0, 0.0, 0.0],
        category="pricing", tags=["giá"],
    ))
    result_sched = await search(vec, linked_kb_tags=["schedule", "giá"])
    assert result_sched is not None
    assert result_sched.article.id == "sched"


# ── campaign_id scoping ───────────────────────────────────────────────────────

CAMP_A = "aaaa-aaaa-aaaa-aaaa"
CAMP_B = "bbbb-bbbb-bbbb-bbbb"


async def test_search_campaign_id_excludes_other_campaign():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="b_art", embedding=vec, threshold=0.8, campaign_id=CAMP_B))
    result = await search(vec, max_threshold=0.8, campaign_id=CAMP_A, linked_kb_tags=["*"])
    assert result is None


async def test_search_campaign_id_includes_own_campaign():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="a_art", embedding=vec, threshold=0.8, campaign_id=CAMP_A))
    result = await search(vec, max_threshold=0.8, campaign_id=CAMP_A, linked_kb_tags=["*"])
    assert result is not None
    assert result.article.id == "a_art"


async def test_search_campaign_id_includes_global_articles():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="global_art", embedding=vec, threshold=0.8, campaign_id=None))
    result = await search(vec, max_threshold=0.8, campaign_id=CAMP_A, linked_kb_tags=["*"])
    assert result is not None
    assert result.article.id == "global_art"


async def test_search_no_campaign_filter_returns_all():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="a_art", embedding=vec, threshold=0.8, campaign_id=CAMP_A))
    store_module._store.append(_article(id="b_art", embedding=vec, threshold=0.8, campaign_id=CAMP_B))
    result = await search(vec, max_threshold=0.8, campaign_id=None, linked_kb_tags=["*"])
    assert result is not None


async def test_search_prefers_campaign_article_over_global_when_both_match():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="global_art", embedding=vec, threshold=0.8, campaign_id=None))
    store_module._store.append(_article(id="a_art", embedding=vec, threshold=0.8, campaign_id=CAMP_A))
    result = await search(vec, max_threshold=0.8, campaign_id=CAMP_A, linked_kb_tags=["*"])
    assert result is not None
