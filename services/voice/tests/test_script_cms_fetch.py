"""Tests for wiring the Script CMS (published campaigns) into real calls.

Before this, the Script CMS (draft/review/publish/lint/audit in Portal) was
completely disconnected from the real call path — the SIP bridge always
loaded a script from a local JSON file, so publish state had no effect on
what a caller actually heard. `_fetch_active_script` closes that gap: when a
call starts with a campaign_id but no inline script, the voice worker fetches
the published version itself from `/internal/scripts/:campaignId/active`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from api.routers.ws import _fetch_active_script

pytestmark = pytest.mark.asyncio


class TestFetchActiveScript:
    async def test_returns_body_on_success(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "v1", "body": {"entry_step": "greeting", "steps": []}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_active_script("campaign-1")

        assert result == {"entry_step": "greeting", "steps": []}
        mock_client.get.assert_awaited_once()
        assert "campaign-1/active" in mock_client.get.call_args.args[0]

    async def test_returns_none_on_404_no_published_version(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock()))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_active_script("campaign-with-no-published-version")

        assert result is None

    async def test_returns_none_on_network_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _fetch_active_script("campaign-1")

        assert result is None
