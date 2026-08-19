"""StreamingRemoteSTT — persistent WebSocket client to the inference server's
`/ws/stt` endpoint for streaming (sliding re-decode) speech-to-text.

Unlike `RemoteSTT` (HTTP one-shot per turn — kept untouched as the fallback),
this class holds ONE WebSocket connection open for the lifetime of a call and
multiplexes turns over it via `turn_id` (reusing `call.turn.TurnOrchestrator`'s
own turn counter — no new turn concept is introduced here).

Feature-flagged via `use_streaming_stt` (default False, see `api/config.py`)
and wired in by `call/media.py::MediaRouter`. This class never silently
swallows a dropped connection: `listen()` raises `StreamingRemoteSTTError` on
an unexpected close so the caller can fall back rather than leave the call in
a silent, hung state (matches the D2 fault-tolerance pattern already used for
`RemoteSTT`/`AudioPipeline`).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

logger = logging.getLogger(__name__)

OnPartial = Callable[[str, str], Awaitable[None]]
"""(turn_id, text) -> None"""

OnFinal = Callable[[str, str, float], Awaitable[None]]
"""(turn_id, text, confidence) -> None"""

OnEndpoint = Callable[[str], Awaitable[None]]
"""(turn_id) -> None"""

_DEFAULT_CONNECT_TIMEOUT_S = 5.0


class StreamingRemoteSTTError(RuntimeError):
    """Raised when the persistent WS connection to the inference server
    fails to open, fails to send, or closes unexpectedly."""


def _to_ws_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    return url


class StreamingRemoteSTT:
    """Long-lived WS client for chunked streaming STT.

    Usage (mirrors `call/media.py::MediaRouter`'s wiring):

        client = StreamingRemoteSTT(base_url, token=token)
        await client.connect()
        listen_task = asyncio.create_task(
            client.listen(on_partial=..., on_final=..., on_endpoint=...)
        )
        await client.start_turn(turn_id)
        await client.send_audio(pcm_bytes)   # repeat as audio arrives
        await client.end_turn()
        ...
        await client.close()
    """

    def __init__(
        self,
        base_url: str,
        token: str = "",
        sample_rate: int = 8000,
        connect_timeout_s: float = _DEFAULT_CONNECT_TIMEOUT_S,
    ) -> None:
        ws_url = f"{_to_ws_url(base_url)}/ws/stt"
        if token:
            ws_url = f"{ws_url}?token={token}"
        self._ws_url = ws_url
        self._token = token
        self._sample_rate = sample_rate
        self._connect_timeout_s = connect_timeout_s
        self._conn: Any = None
        self._closed = True
        # Kept so callers (call/media.py::MediaRouter) can build a plain
        # HTTP RemoteSTT pointed at the same inference server if this
        # streaming connection fails mid-call (D2 degrade-in-call fallback).
        self._base_url = base_url.rstrip("/")

        if not token:
            logger.warning(
                "StreamingRemoteSTT configured without inference_server_token — "
                "connection to %s will be rejected once server-side auth is "
                "enforced",
                self._ws_url,
            )
        logger.info("StreamingRemoteSTT ready (ws_url=%s)", self._ws_url)

    @property
    def is_connected(self) -> bool:
        return self._conn is not None and not self._closed

    @property
    def base_url(self) -> str:
        """The plain HTTP(S) base URL this client was built with (used to
        build a fallback `RemoteSTT` pointed at the same inference server)."""
        return self._base_url

    @property
    def token(self) -> str:
        return self._token

    async def connect(self) -> None:
        """Open the persistent connection. Raises StreamingRemoteSTTError on
        failure — the caller decides whether/how to fall back."""
        try:
            self._conn = await asyncio.wait_for(
                websockets.connect(self._ws_url), timeout=self._connect_timeout_s
            )
        except Exception as exc:
            self._conn = None
            raise StreamingRemoteSTTError(
                f"StreamingRemoteSTT connect to {self._ws_url} failed: {exc}"
            ) from exc
        self._closed = False
        logger.info("StreamingRemoteSTT connected (%s)", self._ws_url)

    async def close(self) -> None:
        """Close the connection deliberately — `listen()` will return
        normally rather than raise once this has been called."""
        self._closed = True
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                await conn.close()
            except Exception:  # pragma: no cover - best-effort teardown
                logger.debug("StreamingRemoteSTT close() raised, ignoring", exc_info=True)

    async def start_turn(self, turn_id: str) -> None:
        await self._send_json(
            {"type": "start_turn", "turn_id": turn_id, "sample_rate": self._sample_rate}
        )

    async def end_turn(self) -> None:
        await self._send_json({"type": "end_turn"})

    async def send_audio(self, pcm_bytes: bytes) -> None:
        """Send one chunk of raw PCM16 audio for the currently open turn."""
        if not pcm_bytes:
            return
        conn = self._require_conn()
        try:
            await conn.send(pcm_bytes)
        except Exception as exc:
            raise StreamingRemoteSTTError(f"StreamingRemoteSTT send_audio failed: {exc}") from exc

    async def _send_json(self, payload: dict[str, Any]) -> None:
        conn = self._require_conn()
        try:
            await conn.send(json.dumps(payload))
        except Exception as exc:
            raise StreamingRemoteSTTError(f"StreamingRemoteSTT send failed: {exc}") from exc

    def _require_conn(self) -> Any:
        if self._conn is None or self._closed:
            raise StreamingRemoteSTTError("StreamingRemoteSTT used before connect() or after close()")
        return self._conn

    async def listen(
        self,
        on_partial: OnPartial | None = None,
        on_final: OnFinal | None = None,
        on_endpoint: OnEndpoint | None = None,
    ) -> None:
        """Consume server events until the connection closes.

        Returns normally only after a deliberate local `close()`. Any other
        disconnect (server crash, Tailscale blip, ...) raises
        `StreamingRemoteSTTError` so `MediaRouter` can fall back instead of
        leaving the call silently hung (D2).
        """
        conn = self._require_conn()
        try:
            async for raw in conn:
                await self._dispatch(raw, on_partial, on_final, on_endpoint)
        except websockets.exceptions.ConnectionClosed as exc:
            if self._closed:
                return
            raise StreamingRemoteSTTError(
                f"StreamingRemoteSTT connection closed unexpectedly: {exc}"
            ) from exc

    async def _dispatch(
        self,
        raw: Any,
        on_partial: OnPartial | None,
        on_final: OnFinal | None,
        on_endpoint: OnEndpoint | None,
    ) -> None:
        try:
            msg = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("StreamingRemoteSTT: dropping malformed message: %r", raw)
            return

        mtype = msg.get("type")
        turn_id = str(msg.get("turn_id", ""))

        if mtype == "stt.partial" and on_partial is not None:
            await on_partial(turn_id, str(msg.get("text", "")))
        elif mtype == "stt.final" and on_final is not None:
            await on_final(turn_id, str(msg.get("text", "")), float(msg.get("confidence", 0.0)))
        elif mtype == "stt.endpoint" and on_endpoint is not None:
            await on_endpoint(turn_id)
