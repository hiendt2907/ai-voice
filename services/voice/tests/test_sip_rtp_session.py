"""RtpSession teardown — regression tests for the "bridge never unwinds"
bug: a real call ended on the SIP side (BYE), but `read_pcm()` kept awaiting
an empty queue forever, so sip/cloudfone_bridge.py never returned, the
CloudFone WebSocket stayed open, and the voice worker never ran its
end-of-call teardown (no call-events posted, session left registered).
"""

from __future__ import annotations

import asyncio

import pytest

from sip.rtp_session import RtpClosedError, RtpSession


def _session() -> RtpSession:
    return RtpSession(local_port=0, remote_ip="127.0.0.1", remote_port=1234)


@pytest.mark.asyncio
async def test_read_pcm_raises_when_closed_while_waiting() -> None:
    session = _session()
    reader = asyncio.create_task(session.read_pcm())
    await asyncio.sleep(0)  # let the reader block on the empty queue

    session.close()

    with pytest.raises(RtpClosedError):
        await asyncio.wait_for(reader, timeout=1)


@pytest.mark.asyncio
async def test_read_pcm_raises_when_already_closed() -> None:
    session = _session()
    session.close()

    with pytest.raises(RtpClosedError):
        await asyncio.wait_for(session.read_pcm(), timeout=1)


@pytest.mark.asyncio
async def test_write_pcm_does_not_block_after_close() -> None:
    session = _session()
    session.close()

    # 400 frames — twice the send queue's capacity. Before the guard this
    # blocked forever, since the send loop that drains it is gone.
    await asyncio.wait_for(session.write_pcm(b"\x00" * 320 * 400), timeout=1)


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    session = _session()
    session.close()
    session.close()

    with pytest.raises(RtpClosedError):
        await asyncio.wait_for(session.read_pcm(), timeout=1)
