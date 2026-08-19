"""Tests for the local inference server (Macbook-side TTS/STT HTTP API).

Models are never loaded: PiperTTS / FasterWhisperSTT are injected as fakes via
FastAPI dependency overrides. ASGITransport skips lifespan, so no warmup runs.
"""

from __future__ import annotations

import os
import struct

# D4 remediation: inference_server refuses to start (raises at import time)
# unless INFERENCE_SERVER_TOKEN is set, so it must be set before the import
# below. Tests use a fixed token and exercise both the happy path and the
# missing/invalid-token rejection paths.
TEST_TOKEN = "test-service-token-do-not-use-in-prod"
os.environ.setdefault("INFERENCE_SERVER_TOKEN", TEST_TOKEN)

import pytest
from httpx import ASGITransport, AsyncClient

from inference_server import INFERENCE_SERVER_TOKEN, app, get_stt, get_tts
from stt.faster_whisper_stt import STTResult

FAKE_PCM = struct.pack("<4h", 0, 1000, -1000, 0)
AUTH_HEADERS = {"Authorization": f"Bearer {INFERENCE_SERVER_TOKEN}"}


class FakePiperTTS:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def synthesize(self, text: str, params: object = None) -> bytes:
        self.calls.append((text, params))
        return FAKE_PCM


class FakeSTT:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, int]] = []

    def transcribe_pcm(self, pcm_bytes: bytes, sample_rate: int = 8000) -> STTResult:
        self.calls.append((pcm_bytes, sample_rate))
        return STTResult(text="xin chào", confidence=0.87, is_final=True)


@pytest.fixture
def fake_tts() -> FakePiperTTS:
    return FakePiperTTS()


@pytest.fixture
def fake_stt() -> FakeSTT:
    return FakeSTT()


@pytest.fixture
async def client(fake_tts: FakePiperTTS, fake_stt: FakeSTT):
    app.dependency_overrides[get_tts] = lambda: fake_tts
    app.dependency_overrides[get_stt] = lambda: fake_stt
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def test_health_returns_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_tts_returns_raw_pcm_with_sample_rate_header(
    client: AsyncClient, fake_tts: FakePiperTTS
) -> None:
    resp = await client.post(
        "/tts/synthesize",
        json={"text": "Xin chào", "speaking_rate": 1.2, "pitch": None},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/L16"
    assert resp.headers["x-sample-rate"] == "8000"
    assert resp.content == FAKE_PCM
    text, params = fake_tts.calls[0]
    assert text == "Xin chào"
    assert params.speaking_rate == 1.2


async def test_tts_defaults_speaking_rate_when_null(
    client: AsyncClient, fake_tts: FakePiperTTS
) -> None:
    resp = await client.post("/tts/synthesize", json={"text": "a"}, headers=AUTH_HEADERS)

    assert resp.status_code == 200
    assert fake_tts.calls[0][1].speaking_rate == 1.0


async def test_tts_rejects_empty_text(client: AsyncClient) -> None:
    resp = await client.post("/tts/synthesize", json={"text": ""}, headers=AUTH_HEADERS)

    assert resp.status_code == 422


async def test_stt_transcribes_raw_pcm_body(
    client: AsyncClient, fake_stt: FakeSTT
) -> None:
    resp = await client.post(
        "/stt/transcribe?sample_rate=16000",
        content=FAKE_PCM,
        headers={"Content-Type": "application/octet-stream", **AUTH_HEADERS},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "text": "xin chào",
        "confidence": 0.87,
        "is_final": True,
        "language": "vi",
        "emotion": None,
    }
    assert fake_stt.calls == [(FAKE_PCM, 16000)]


async def test_stt_defaults_sample_rate_to_8000(
    client: AsyncClient, fake_stt: FakeSTT
) -> None:
    resp = await client.post(
        "/stt/transcribe",
        content=b"",
        headers={"Content-Type": "application/octet-stream", **AUTH_HEADERS},
    )

    assert resp.status_code == 200
    assert fake_stt.calls[0][1] == 8000


# --- D4: authentication -----------------------------------------------------


async def test_tts_rejects_missing_authorization_header(client: AsyncClient) -> None:
    resp = await client.post("/tts/synthesize", json={"text": "a"})

    assert resp.status_code == 401


async def test_tts_rejects_wrong_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/tts/synthesize",
        json={"text": "a"},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert resp.status_code == 401


async def test_tts_rejects_malformed_authorization_header(client: AsyncClient) -> None:
    resp = await client.post(
        "/tts/synthesize",
        json={"text": "a"},
        headers={"Authorization": INFERENCE_SERVER_TOKEN},  # missing "Bearer " prefix
    )

    assert resp.status_code == 401


async def test_stt_rejects_missing_authorization_header(client: AsyncClient) -> None:
    resp = await client.post(
        "/stt/transcribe",
        content=FAKE_PCM,
        headers={"Content-Type": "application/octet-stream"},
    )

    assert resp.status_code == 401


async def test_stt_rejects_wrong_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/stt/transcribe",
        content=FAKE_PCM,
        headers={
            "Content-Type": "application/octet-stream",
            "Authorization": "Bearer wrong-token",
        },
    )

    assert resp.status_code == 401


async def test_health_does_not_require_authorization(client: AsyncClient) -> None:
    resp = await client.get("/health")

    assert resp.status_code == 200


# --- D4: request size cap on /stt/transcribe --------------------------------


async def test_stt_rejects_body_exceeding_size_cap_via_content_length(
    client: AsyncClient,
) -> None:
    from inference_server import MAX_STT_BODY_BYTES

    oversized = b"\x00" * (MAX_STT_BODY_BYTES + 1)
    resp = await client.post(
        "/stt/transcribe",
        content=oversized,
        headers={"Content-Type": "application/octet-stream", **AUTH_HEADERS},
    )

    assert resp.status_code == 413
