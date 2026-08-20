"""Tests for RemoteTTS / RemoteSTT — HTTP adapters to the inference server.

No network: httpx.MockTransport serves the fake inference server.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from stt.remote_stt import RemoteSTT, RemoteSTTError
from tts.params import TTSParams
from tts.remote_tts import RemoteTTS, RemoteTTSError

BASE = "http://inference.test:8100"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------------- TTS


async def test_tts_synthesize_returns_pcm_bytes():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = request.read().decode()
        return httpx.Response(200, content=b"\x01\x02" * 8, headers={"content-type": "audio/L16"})

    tts = RemoteTTS(base_url=BASE + "/", client=_client(handler))
    pcm = await tts.synthesize("xin chào", TTSParams(speaking_rate=1.2))

    assert pcm == b"\x01\x02" * 8
    assert seen["url"] == f"{BASE}/tts/synthesize"
    assert '"speaking_rate":1.2' in str(seen["json"])


async def test_tts_empty_text_skips_request():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not be called")

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    assert await tts.synthesize("   ") == b""


async def test_tts_http_error_raises_remote_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    with pytest.raises(RemoteTTSError, match="HTTP 500"):
        await tts.synthesize("xin chào")


async def test_tts_connect_error_raises_remote_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    with pytest.raises(RemoteTTSError, match="unreachable"):
        await tts.synthesize("xin chào")


async def test_tts_stream_synthesize_chunks():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"a" * 2500)

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    gen = await tts.stream_synthesize("xin chào", chunk_size=1000)
    chunks = [c async for c in gen]

    assert [len(c) for c in chunks] == [1000, 1000, 500]


async def test_tts_stream_synthesize_hits_streaming_endpoint():
    """stream_synthesize must call the true-streaming endpoint, not the
    one-shot /tts/synthesize used by synthesize() — regression guard for
    the pseudo-stream fix (architecture doc §197/§1074/§1182)."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, content=b"chunk")

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    gen = await tts.stream_synthesize("xin chào")
    [c async for c in gen]

    assert seen["url"] == f"{BASE}/tts/synthesize/stream"


async def test_tts_stream_synthesize_yields_chunks_as_server_sends_them():
    """The client must consume the response incrementally (httpx streaming),
    not buffer the whole body first — otherwise the transport-layer fix is
    a no-op regardless of what the server does."""

    async def body():
        yield b"first-sentence-"
        yield b"second-sentence"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body())

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    gen = await tts.stream_synthesize("xin chào", chunk_size=64)
    chunks = [c async for c in gen]

    assert b"".join(chunks) == b"first-sentence-second-sentence"


async def test_tts_stream_synthesize_http_error_raises_remote_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    gen = await tts.stream_synthesize("xin chào")
    with pytest.raises(RemoteTTSError, match="HTTP 500"):
        [c async for c in gen]


async def test_tts_stream_synthesize_connect_error_raises_remote_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    gen = await tts.stream_synthesize("xin chào")
    with pytest.raises(RemoteTTSError, match="unreachable"):
        [c async for c in gen]


async def test_tts_stream_synthesize_empty_text_yields_nothing():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not be called")

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    gen = await tts.stream_synthesize("   ")
    assert [c async for c in gen] == []


async def test_tts_stream_step_joins_beats_and_fills_slots():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200, content=b"pcm-data")

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    beats = [
        {"text": "Chào {{name}}", "pause_after": "short"},
        {"text": "", "pause_after": "none"},
        {"text": "Xin nghe", "pause_after": "turn"},
    ]
    gen = await tts.stream_step(beats, {"name": "Hiền"})
    out = b"".join([c async for c in gen])

    assert out == b"pcm-data"
    assert "Chào Hiền, Xin nghe" in seen["body"]


async def test_tts_stream_step_empty_beats_yields_nothing():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not be called")

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    gen = await tts.stream_step([{"text": "  "}])
    assert [c async for c in gen] == []


async def test_tts_stream_step_stops_on_interrupt():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"z" * 4000)

    tts = RemoteTTS(base_url=BASE, client=_client(handler))
    interrupt = asyncio.Event()
    interrupt.set()
    gen = await tts.stream_step([{"text": "hello"}], {}, interrupt)
    assert [c async for c in gen] == []


async def test_tts_aclose_owned_client():
    tts = RemoteTTS(base_url=BASE)
    tts._get_client()
    await tts.aclose()
    assert tts._client is None


# --------------------------------------------------------------------------- STT


async def test_stt_transcribe_parses_result():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "text": "xin chào",
                "confidence": 0.91,
                "is_final": True,
                "language": "vi",
                "emotion": "happy",
            },
        )

    stt = RemoteSTT(base_url=BASE, client=_client(handler))
    result = await stt.transcribe_pcm(b"\x00\x01" * 10, sample_rate=8000)

    assert result.text == "xin chào"
    assert result.confidence == pytest.approx(0.91)
    assert result.is_final is True
    assert result.language == "vi"
    assert result.emotion == "happy"
    assert "sample_rate=8000" in str(seen["url"])
    assert seen["body"] == b"\x00\x01" * 10


async def test_stt_empty_pcm_short_circuits():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("should not be called")

    stt = RemoteSTT(base_url=BASE, client=_client(handler))
    result = await stt.transcribe_pcm(b"")
    assert result.text == ""
    assert result.confidence == 0.0


async def test_stt_defaults_on_partial_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "a"})

    stt = RemoteSTT(base_url=BASE, client=_client(handler))
    result = await stt.transcribe_pcm(b"\x00\x01")
    assert result.confidence == 0.0
    assert result.language == "vi"
    assert result.emotion is None


async def test_stt_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    stt = RemoteSTT(base_url=BASE, client=_client(handler))
    with pytest.raises(RemoteSTTError, match="HTTP 503"):
        await stt.transcribe_pcm(b"\x00\x01")


async def test_stt_connect_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    stt = RemoteSTT(base_url=BASE, client=_client(handler))
    with pytest.raises(RemoteSTTError, match="unreachable"):
        await stt.transcribe_pcm(b"\x00\x01")


async def test_stt_invalid_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})

    stt = RemoteSTT(base_url=BASE, client=_client(handler))
    with pytest.raises(RemoteSTTError, match="invalid JSON"):
        await stt.transcribe_pcm(b"\x00\x01")


async def test_stt_is_async_for_pipeline_detection():
    import inspect

    assert inspect.iscoroutinefunction(RemoteSTT.transcribe_pcm)


async def test_stt_aclose_owned_client():
    stt = RemoteSTT(base_url=BASE)
    stt._get_client()
    await stt.aclose()
    assert stt._client is None
