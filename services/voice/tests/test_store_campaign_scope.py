"""Part A — voice worker must scope KB/NLU export by campaign.

Verifies reload_from_api() forwards campaignId as a query param to the NestJS
internal endpoint, so a call only loads its own campaign's resources.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag import store as rag_store
from nlu import store as nlu_store

CAMPAIGN_A = "11111111-1111-1111-1111-111111111111"


def _patch_async_client(monkeypatch, target, captured: dict) -> None:
    """Patch httpx.AsyncClient in `target` module to capture get() params."""

    async def fake_get(url, params=None):
        captured["url"] = url
        captured["params"] = params
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=[])
        return resp

    @asynccontextmanager
    async def fake_client(*_args, **_kwargs):
        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        yield client

    monkeypatch.setattr(target.httpx, "AsyncClient", fake_client)


@pytest.mark.asyncio
async def test_rag_reload_forwards_campaign_id(monkeypatch):
    captured: dict = {}
    _patch_async_client(monkeypatch, rag_store, captured)

    await rag_store.reload_from_api("http://api", campaign_id=CAMPAIGN_A)

    assert captured["url"].endswith("/internal/knowledge/rag-export")
    assert captured["params"] == {"campaignId": CAMPAIGN_A}


@pytest.mark.asyncio
async def test_rag_reload_no_campaign_sends_empty_params(monkeypatch):
    captured: dict = {}
    _patch_async_client(monkeypatch, rag_store, captured)

    await rag_store.reload_from_api("http://api")

    assert captured["params"] == {}


@pytest.mark.asyncio
async def test_nlu_reload_forwards_campaign_id(monkeypatch):
    captured: dict = {}
    _patch_async_client(monkeypatch, nlu_store, captured)

    await nlu_store.reload_from_api("http://api", campaign_id=CAMPAIGN_A)

    assert captured["url"].endswith("/internal/nlu/export")
    assert captured["params"] == {"campaignId": CAMPAIGN_A}
