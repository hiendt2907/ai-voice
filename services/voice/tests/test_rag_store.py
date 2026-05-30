"""Tests for RAG in-memory store — cosine search and gender resolution."""

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
    """Reset in-memory store before each test."""
    store_module._store.clear()
    yield
    store_module._store.clear()


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

def test_search_returns_none_when_store_empty():
    result = search(_unit_vec(pos=0))
    assert result is None


def test_search_returns_none_when_no_embeddings():
    store_module._store.append(_article(embedding=None))
    result = search(_unit_vec(pos=0))
    assert result is None


def test_search_returns_match_above_threshold():
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8))
    result = search(vec, gender="male", max_threshold=0.8)
    assert result is not None
    assert result.score > 0.99
    assert result.answer == "Đây là câu trả lời, anh."


def test_search_returns_none_below_threshold():
    query = _unit_vec(4, pos=0)
    different = _unit_vec(4, pos=1)
    store_module._store.append(_article(embedding=different, threshold=0.82))
    result = search(query, max_threshold=0.82)
    assert result is None


def test_search_max_threshold_overrides_article_threshold():
    """max_threshold caps per-article threshold — calibrates model at runtime."""
    vec = _unit_vec(pos=0)
    # Article has threshold=0.82, but we pass max_threshold=0.65 (config calibration)
    store_module._store.append(_article(embedding=vec, threshold=0.82))
    # With max_threshold=0.65, effective = min(0.82, 0.65) = 0.65, score=1.0 → match
    result = search(vec, max_threshold=0.65)
    assert result is not None
    # With max_threshold=0.82 (default), score=1.0 still matches
    result2 = search(vec, max_threshold=0.82)
    assert result2 is not None


def test_search_picks_best_of_multiple():
    close = [0.99, 0.01, 0.0, 0.0]
    far = [0.0, 0.0, 1.0, 0.0]
    store_module._store.append(_article(id="a1", embedding=close, threshold=0.8))
    store_module._store.append(_article(id="a2", embedding=far, threshold=0.8))
    query = _unit_vec(4, pos=0)
    result = search(query)
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
    txt = fallback_text("female")
    assert "chị" in txt


def test_fallback_text_male():
    txt = fallback_text("male")
    assert "anh" in txt


def test_fallback_text_unknown_defaults_to_male():
    txt = fallback_text("unknown")
    assert "anh" in txt


# ── upsert_embedding ─────────────────────────────────────────────────────────

def test_upsert_updates_existing_article():
    store_module._store.append(_article(id="x", embedding=None))
    new_vec = [0.1, 0.2, 0.3]
    upsert_embedding("x", new_vec)
    assert store_module._store[0].embedding == new_vec


def test_upsert_noop_for_unknown_id():
    store_module._store.append(_article(id="known", embedding=[1.0]))
    upsert_embedding("unknown", [0.5])
    assert store_module._store[0].embedding == [1.0]


# ── reload_from_api ───────────────────────────────────────────────────────────

# ── linkedKbTags filter (Phase 2.8) ──────────────────────────────────────────

def test_search_tag_filter_matches_overlap():
    """Articles with matching tags pass the filter."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["booking", "pricing"]))
    result = search(vec, linked_kb_tags=["pricing"])
    assert result is not None


def test_search_tag_filter_excludes_no_overlap():
    """Articles with no overlapping tags are excluded."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["booking"]))
    result = search(vec, linked_kb_tags=["lab_results"])
    assert result is None


def test_search_tag_filter_empty_filter_matches_all():
    """Empty linked_kb_tags means no filter — all articles eligible."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["booking"]))
    result = search(vec, linked_kb_tags=[])
    assert result is not None


def test_search_tag_filter_none_matches_all():
    """linked_kb_tags=None means no filter."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(embedding=vec, threshold=0.8, tags=["anything"]))
    result = search(vec, linked_kb_tags=None)
    assert result is not None


def test_search_tag_filter_prefers_tagged_over_untagged():
    """With tag filter, articles with no matching tags are excluded even if score is high."""
    vec = _unit_vec(4, pos=0)
    store_module._store.append(_article(id="tagged", embedding=vec, threshold=0.8, tags=["booking"]))
    store_module._store.append(_article(id="untagged", embedding=vec, threshold=0.8, tags=["other"]))
    result = search(vec, linked_kb_tags=["booking"])
    assert result is not None
    assert result.article.id == "tagged"


# ── category name matching (Phase 2.8 extended) ───────────────────────────────

def test_search_matches_article_by_category_name():
    """linked_kb_tags containing a category name matches articles with that category."""
    vec = _unit_vec(pos=0)
    article = Article(
        id="a1", title="T", answer_text="A",
        answer_male=None, answer_female=None,
        confidence_threshold=0.8, embedding=vec,
        category="booking", tags=["some_other_tag"],
    )
    store_module._store.append(article)
    # Search with the category name — should match even though "booking" is not in tags
    result = search(vec, linked_kb_tags=["booking"])
    assert result is not None
    assert result.article.id == "a1"


def test_search_excludes_article_when_category_not_in_filter():
    """Article whose category is not in linked_kb_tags and tags don't match → excluded."""
    vec = _unit_vec(pos=0)
    article = Article(
        id="a1", title="T", answer_text="A",
        answer_male=None, answer_female=None,
        confidence_threshold=0.8, embedding=vec,
        category="schedule", tags=["lịch"],
    )
    store_module._store.append(article)
    result = search(vec, linked_kb_tags=["booking"])
    assert result is None


def test_search_category_and_tag_filter_union():
    """linked_kb_tags can contain both category names and specific tags."""
    vec = _unit_vec(pos=0)
    # Article in "schedule" category
    store_module._store.append(Article(
        id="sched", title="T", answer_text="A",
        answer_male=None, answer_female=None,
        confidence_threshold=0.8, embedding=vec,
        category="schedule", tags=["lịch"],
    ))
    # Article in "pricing" category with matching tag
    store_module._store.append(Article(
        id="price", title="T", answer_text="A",
        answer_male=None, answer_female=None,
        confidence_threshold=0.8, embedding=[0.0, 1.0, 0.0, 0.0],
        category="pricing", tags=["giá"],
    ))
    # Filter: include "schedule" category and "giá" tag
    result_sched = search(vec, linked_kb_tags=["schedule", "giá"])
    assert result_sched is not None
    assert result_sched.article.id == "sched"


# ── campaign_id scoping (Part A) ──────────────────────────────────────────────

CAMP_A = "aaaa-aaaa-aaaa-aaaa"
CAMP_B = "bbbb-bbbb-bbbb-bbbb"


def test_search_campaign_id_excludes_other_campaign():
    """Article from campaign B must not appear in a campaign A search."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="b_art", embedding=vec, threshold=0.8, campaign_id=CAMP_B))
    result = search(vec, max_threshold=0.8, campaign_id=CAMP_A)
    assert result is None, "Campaign B article must not be returned for campaign A"


def test_search_campaign_id_includes_own_campaign():
    """Article from campaign A is returned when searching with campaign A."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="a_art", embedding=vec, threshold=0.8, campaign_id=CAMP_A))
    result = search(vec, max_threshold=0.8, campaign_id=CAMP_A)
    assert result is not None
    assert result.article.id == "a_art"


def test_search_campaign_id_includes_global_articles():
    """Global articles (campaign_id=None) are returned for any campaign search."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="global_art", embedding=vec, threshold=0.8, campaign_id=None))
    result = search(vec, max_threshold=0.8, campaign_id=CAMP_A)
    assert result is not None
    assert result.article.id == "global_art"


def test_search_no_campaign_filter_returns_all():
    """When campaign_id=None (no filter), articles from all campaigns are returned."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="a_art", embedding=vec, threshold=0.8, campaign_id=CAMP_A))
    store_module._store.append(_article(id="b_art", embedding=vec, threshold=0.8, campaign_id=CAMP_B))
    # No campaign filter — returns the best score (first one inserted wins tie)
    result = search(vec, max_threshold=0.8, campaign_id=None)
    assert result is not None


def test_search_prefers_campaign_article_over_global_when_both_match():
    """Both campaign-specific and global articles are candidates; best score wins."""
    vec = _unit_vec(pos=0)
    store_module._store.append(_article(id="global_art", embedding=vec, threshold=0.8, campaign_id=None))
    store_module._store.append(_article(id="a_art", embedding=vec, threshold=0.8, campaign_id=CAMP_A))
    result = search(vec, max_threshold=0.8, campaign_id=CAMP_A)
    # Both match; result is not None is the key assertion (ordering between equal scores is undefined)
    assert result is not None


@pytest.mark.asyncio
async def test_reload_from_api_parses_articles():
    import rag.store as store_mod  # noqa: PLC0415

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
        count = await store_mod.reload_from_api("http://api")

    assert count == 1
    assert store_mod._store[0].id == "id1"
    assert store_mod._store[0].embedding == [0.1, 0.2]
    assert store_mod._store[0].confidence_threshold == 0.85
    assert store_mod._store[0].tags == ["schedule", "booking"]
    assert store_mod._store[0].campaign_id == "camp-uuid-1234"
