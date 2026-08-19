"""Tests for StreamingRemoteSTT (Phase 2, D2/D5) — the GCP-side persistent
WS client for the inference server's /ws/stt gateway.

A tiny local `websockets.serve` server plays the role of the inference
server so these tests exercise the real wire protocol without needing a
loaded STT model or a Macbook connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest
import websockets

from stt.streaming_remote_stt import StreamingRemoteSTT, StreamingRemoteSTTError

pytestmark = pytest.mark.asyncio


async def _echo_protocol_server(websocket) -> None:
    """Replays the real /ws/stt happy path: start_turn -> (ignore audio) ->
    end_turn -> stt.final."""
    turn_id = None
    async for raw in websocket:
        if isinstance(raw, bytes):
            continue  # audio chunk — real server would buffer it
        msg = json.loads(raw)
        if msg["type"] == "start_turn":
            turn_id = msg["turn_id"]
            await websocket.send(json.dumps({"type": "stt.partial", "turn_id": turn_id, "text": "xin"}))
        elif msg["type"] == "end_turn":
            await websocket.send(
                json.dumps(
                    {"type": "stt.final", "turn_id": turn_id, "text": "xin chào", "confidence": 0.8}
                )
            )
            return  # end of turn, server would keep the socket open for more turns
            # (return here just ends this test server's handler)


async def _abrupt_close_server(websocket) -> None:
    await websocket.recv()  # wait for the first message (start_turn)
    await websocket.close(code=1011)  # simulate a server crash mid-turn


@pytest.fixture
async def server_factory():
    """Yields a function that starts a local websockets server running the
    given handler and returns its base_url (http://host:port form, matching
    what StreamingRemoteSTT expects)."""
    servers: list[websockets.WebSocketServer] = []

    async def _start(handler):
        server = await websockets.serve(handler, "127.0.0.1", 0)
        servers.append(server)
        port = server.sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    yield _start

    for server in servers:
        server.close()
        await server.wait_closed()


async def test_connect_translates_http_url_to_ws(server_factory) -> None:
    base_url = await server_factory(_echo_protocol_server)
    client = StreamingRemoteSTT(base_url, token="t")

    assert client._ws_url.startswith("ws://")  # noqa: SLF001 — asserting internal URL translation

    await client.connect()
    assert client.is_connected
    await client.close()
    assert not client.is_connected


async def test_start_turn_send_audio_end_turn_round_trip(server_factory) -> None:
    base_url = await server_factory(_echo_protocol_server)
    client = StreamingRemoteSTT(base_url, token="t")
    await client.connect()

    partials: list[tuple[str, str]] = []
    finals: list[tuple[str, str, float]] = []

    async def on_partial(turn_id: str, text: str) -> None:
        partials.append((turn_id, text))

    async def on_final(turn_id: str, text: str, confidence: float) -> None:
        finals.append((turn_id, text, confidence))

    listen_task = asyncio.create_task(client.listen(on_partial=on_partial, on_final=on_final))

    await client.start_turn("turn-1")
    await client.send_audio(b"\x00\x01" * 100)
    await client.end_turn()

    await asyncio.wait_for(listen_task, timeout=2.0)
    await client.close()

    assert partials == [("turn-1", "xin")]
    assert finals == [("turn-1", "xin chào", 0.8)]


async def test_send_audio_before_connect_raises(server_factory) -> None:
    client = StreamingRemoteSTT("http://127.0.0.1:1", token="t")

    with pytest.raises(StreamingRemoteSTTError):
        await client.send_audio(b"\x00\x01")


async def test_connect_to_unreachable_server_raises(server_factory) -> None:
    client = StreamingRemoteSTT("http://127.0.0.1:1", token="t", connect_timeout_s=1.0)

    with pytest.raises(StreamingRemoteSTTError):
        await client.connect()


async def test_unexpected_disconnect_raises_not_hangs(server_factory) -> None:
    """D2: an unexpected disconnect must surface as an error the caller can
    fall back on — never a task that silently hangs forever."""
    base_url = await server_factory(_abrupt_close_server)
    client = StreamingRemoteSTT(base_url, token="t")
    await client.connect()

    await client.start_turn("turn-x")

    with pytest.raises(StreamingRemoteSTTError):
        await asyncio.wait_for(client.listen(), timeout=2.0)


async def test_deliberate_close_makes_listen_return_normally(server_factory) -> None:
    async def _hold_open_server(websocket) -> None:
        with contextlib.suppress(Exception):
            await websocket.wait_closed()

    base_url = await server_factory(_hold_open_server)
    client = StreamingRemoteSTT(base_url, token="t")
    await client.connect()

    listen_task = asyncio.create_task(client.listen())
    await asyncio.sleep(0.05)  # let listen() actually start consuming
    await client.close()

    # Must complete without raising — a local close() is not an error.
    await asyncio.wait_for(listen_task, timeout=2.0)


async def test_no_token_still_connects_but_logs_warning(server_factory, caplog) -> None:
    base_url = await server_factory(_echo_protocol_server)
    client = StreamingRemoteSTT(base_url, token="")

    await client.connect()
    assert client.is_connected
    await client.close()
