"""One RTP media session (one call) — asyncio UDP, G.711 in/out.

Exposes read_pcm()/write_pcm() in 16-bit signed linear PCM @ 8kHz (matches
the rest of the pipeline — audio/codec.py, call/egress.py — exactly, no
8-bit-unsigned detour). Encode/decode reuses audio/codec.py's numpy G.711
implementation (no `audioop`, unlike most Python SIP libraries — that
module is removed in Python 3.13+).
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from audio.codec import pcm_to_ulaw, ulaw_to_pcm
from sip.rtp import SequenceCounter, build, new_ssrc, parse

logger = logging.getLogger(__name__)

_FRAME_MS = 20
_FRAME_INTERVAL_S = _FRAME_MS / 1000
_BYTES_PER_FRAME = 320  # 160 samples * 2 bytes (int16) @ 8kHz/20ms
_PT_PCMU = 0


class _RtpProtocol(asyncio.DatagramProtocol):
    def __init__(self, session: RtpSession) -> None:
        self._session = session
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._session._on_datagram(data)

    def error_received(self, exc: Exception) -> None:
        logger.warning("RTP socket error: %s", exc)


class RtpSession:
    """Bound to one local UDP port for the lifetime of one call."""

    def __init__(self, local_port: int, remote_ip: str, remote_port: int) -> None:
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _RtpProtocol | None = None
        self._ssrc = new_ssrc()
        self._seq = SequenceCounter()
        self._inbound: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self._send_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self._send_task: asyncio.Task | None = None
        self._closed = False

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _RtpProtocol(self),
            local_addr=("0.0.0.0", self.local_port),  # noqa: S104 — telephony host, all interfaces by design
        )
        self._send_task = asyncio.create_task(self._send_loop())
        logger.info("RTP session started: local=%d remote=%s:%d", self.local_port, self.remote_ip, self.remote_port)

    def _on_datagram(self, data: bytes) -> None:
        packet = parse(data)
        if packet is None or not packet.payload:
            return
        ulaw = np.frombuffer(packet.payload, dtype=np.uint8)
        pcm = ulaw_to_pcm(ulaw.tobytes())
        try:
            self._inbound.put_nowait(pcm.tobytes())
        except asyncio.QueueFull:
            pass  # drop oldest-style backpressure: just skip this frame

    async def read_pcm(self) -> bytes:
        """One 20ms frame of 16-bit signed linear PCM @ 8kHz (320 bytes)."""
        return await self._inbound.get()

    async def write_pcm(self, data: bytes) -> None:
        """Queue linear PCM for playback; chunked into 20ms RTP frames by
        the send loop so pacing stays correct regardless of caller chunk size."""
        for i in range(0, len(data), _BYTES_PER_FRAME):
            chunk = data[i : i + _BYTES_PER_FRAME]
            if len(chunk) < _BYTES_PER_FRAME:
                chunk = chunk + b"\x00" * (_BYTES_PER_FRAME - len(chunk))
            await self._send_queue.put(chunk)

    def flush_playback(self) -> None:
        """Barge-in: drop whatever's queued for playback right now."""
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _send_loop(self) -> None:
        assert self._transport is not None
        next_send = asyncio.get_running_loop().time()
        sent_count = 0
        logger.debug("RTP send target: %s:%d", self.remote_ip, self.remote_port)
        while not self._closed:
            try:
                pcm_chunk = await asyncio.wait_for(self._send_queue.get(), timeout=_FRAME_INTERVAL_S)
            except TimeoutError:
                continue  # nothing queued — send nothing (no silence-filler needed for our use case)

            pcm = np.frombuffer(pcm_chunk, dtype=np.int16)
            ulaw = pcm_to_ulaw(pcm)
            seq, ts = self._seq.next()
            packet = build(
                payload_type=_PT_PCMU, sequence=seq, timestamp=ts, ssrc=self._ssrc, payload=ulaw
            )

            now = asyncio.get_running_loop().time()
            wait = next_send - now
            if wait > 0:
                await asyncio.sleep(wait)
            sent_count += 1
            if sent_count <= 3 or sent_count % 250 == 0:
                logger.debug(
                    "RTP send #%d: %d bytes payload to %s:%d (seq=%d ts=%d)",
                    sent_count, len(ulaw), self.remote_ip, self.remote_port, seq, ts,
                )
            self._transport.sendto(packet, (self.remote_ip, self.remote_port))
            next_send = max(next_send + _FRAME_INTERVAL_S, now)

    def close(self) -> None:
        self._closed = True
        if self._send_task:
            self._send_task.cancel()
        if self._transport:
            self._transport.close()
