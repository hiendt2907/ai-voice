"""Test header xác thực cho /internal/*."""

from __future__ import annotations

from api.internal_auth import internal_headers, _settings


class TestInternalHeaders:
    def test_includes_key_when_service_api_key_set(self, monkeypatch):
        monkeypatch.setattr(_settings, "service_api_key", "sk-test-123")
        monkeypatch.setattr(_settings, "internal_api_key", "")

        headers = internal_headers()

        assert headers["x-internal-key"] == "sk-test-123"

    def test_falls_back_to_internal_api_key(self, monkeypatch):
        monkeypatch.setattr(_settings, "service_api_key", "")
        monkeypatch.setattr(_settings, "internal_api_key", "ik-test-456")

        headers = internal_headers()

        assert headers["x-internal-key"] == "ik-test-456"

    def test_service_api_key_takes_priority(self, monkeypatch):
        monkeypatch.setattr(_settings, "service_api_key", "sk-first")
        monkeypatch.setattr(_settings, "internal_api_key", "ik-second")

        headers = internal_headers()

        assert headers["x-internal-key"] == "sk-first"

    def test_no_key_omits_header(self, monkeypatch):
        monkeypatch.setattr(_settings, "service_api_key", "")
        monkeypatch.setattr(_settings, "internal_api_key", "")

        headers = internal_headers()

        assert "x-internal-key" not in headers

    def test_extra_headers_preserved(self, monkeypatch):
        monkeypatch.setattr(_settings, "service_api_key", "sk-test")
        monkeypatch.setattr(_settings, "internal_api_key", "")

        headers = internal_headers({"Content-Type": "application/json"})

        assert headers["Content-Type"] == "application/json"
        assert headers["x-internal-key"] == "sk-test"
