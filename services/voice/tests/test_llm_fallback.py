"""Test chuỗi fallback model của LLMClient."""

from __future__ import annotations

import httpx
import pytest

from llm.client import LLMClient


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://x/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


class _FakePost:
    """Giả lập /chat/completions: tra kết quả theo tên model trong payload."""

    def __init__(self, outcomes: dict[str, object]) -> None:
        self._outcomes = outcomes
        self.calls: list[str] = []

    async def __call__(self, url: str, json: dict) -> httpx.Response:
        model = json["model"]
        self.calls.append(model)
        outcome = self._outcomes.get(model, _http_error(503))
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": outcome}}]},
            request=httpx.Request("POST", url),
        )


def _client(monkeypatch, outcomes: dict[str, object], **kw) -> tuple[LLMClient, _FakePost]:
    c = LLMClient(
        base_url="https://x/v1",
        model="primary",
        api_key="k",
        fallback_models=["second", "third"],
        **kw,
    )
    fake = _FakePost(outcomes)
    monkeypatch.setattr(c._client, "post", fake)
    return c, fake


class TestChatFallback:
    async def test_uses_primary_when_healthy(self, monkeypatch):
        c, fake = _client(monkeypatch, {"primary": "ok-1"})

        assert await c.chat([{"role": "user", "content": "hi"}]) == "ok-1"
        assert fake.calls == ["primary"]

    async def test_falls_through_to_next_model_on_503(self, monkeypatch):
        c, fake = _client(monkeypatch, {"primary": _http_error(503), "second": "ok-2"})

        assert await c.chat([{"role": "user", "content": "hi"}]) == "ok-2"
        assert fake.calls == ["primary", "second"]

    async def test_empty_content_treated_as_failure(self, monkeypatch):
        """HTTP 200 + content rỗng (gặp thật với glm-4.6) không được coi là thành công."""
        c, fake = _client(monkeypatch, {"primary": "   ", "second": "ok-2"})

        assert await c.chat([{"role": "user", "content": "hi"}]) == "ok-2"
        assert fake.calls == ["primary", "second"]

    async def test_raises_when_every_model_fails(self, monkeypatch):
        c, _ = _client(
            monkeypatch,
            {m: _http_error(503) for m in ("primary", "second", "third")},
        )

        with pytest.raises(RuntimeError, match="Tất cả model"):
            await c.chat([{"role": "user", "content": "hi"}])

    async def test_duplicate_models_are_not_tried_twice(self, monkeypatch):
        c = LLMClient(
            base_url="https://x/v1",
            model="primary",
            api_key="k",
            fallback_models=["primary", "second"],
        )
        fake = _FakePost({"primary": _http_error(503), "second": "ok-2"})
        monkeypatch.setattr(c._client, "post", fake)

        await c.chat([{"role": "user", "content": "hi"}])

        assert fake.calls == ["primary", "second"]


class TestBreaker:
    async def test_dead_model_skipped_after_threshold(self, monkeypatch):
        """Mấu chốt: model chết không được thử lại ở MỌI lượt thoại.

        Mỗi lần thử một model chết là cộng một round-trip vào độ trễ của câu
        khách đang nói.
        """
        c, fake = _client(monkeypatch, {"primary": _http_error(503), "second": "ok-2"})

        for _ in range(4):
            await c.chat([{"role": "user", "content": "hi"}])

        # 2 lần đầu chạm "primary" rồi cầu dao ngắt; 2 lượt sau đi thẳng "second".
        assert fake.calls.count("primary") == 2
        assert fake.calls.count("second") == 4

    async def test_permanent_error_opens_breaker_immediately(self, monkeypatch):
        """403 'requires a paid account' sẽ không tự khỏi — ngắt ngay từ lần đầu."""
        c, fake = _client(monkeypatch, {"primary": _http_error(403), "second": "ok-2"})

        await c.chat([{"role": "user", "content": "hi"}])
        await c.chat([{"role": "user", "content": "hi"}])

        assert fake.calls.count("primary") == 1

    async def test_success_resets_failure_count(self, monkeypatch):
        outcomes: dict[str, object] = {"primary": _http_error(503), "second": "ok-2"}
        c, fake = _client(monkeypatch, outcomes)

        await c.chat([{"role": "user", "content": "hi"}])  # primary lỗi lần 1
        outcomes["primary"] = "ok-1"
        await c.chat([{"role": "user", "content": "hi"}])  # primary khỏi
        outcomes["primary"] = _http_error(503)
        await c.chat([{"role": "user", "content": "hi"}])  # lỗi lần 1 (đã reset)

        assert fake.calls.count("primary") == 3, "đếm lỗi phải reset sau khi thành công"

    async def test_all_open_still_attempts_rather_than_refusing(self, monkeypatch):
        outcomes: dict[str, object] = {
            m: _http_error(503) for m in ("primary", "second", "third")
        }
        c, fake = _client(monkeypatch, outcomes)

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await c.chat([{"role": "user", "content": "hi"}])

        outcomes["third"] = "ok-3"
        # Dù cả ba đang bị ngắt, vẫn phải thử — thà chậm còn hơn im lặng.
        assert await c.chat([{"role": "user", "content": "hi"}]) == "ok-3"

    def test_model_status_reports_every_configured_model(self, monkeypatch):
        c, _ = _client(monkeypatch, {})

        assert set(c.model_status()) == {"primary", "second", "third"}
        assert all(v == "closed" for v in c.model_status().values())
