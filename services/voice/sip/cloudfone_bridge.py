"""Bridges one real SIP/RTP call (sip/client.py + sip/rtp_session.py, running
on the Macbook — the only IP voip24h accepts) to the AI pipeline running on
GCP (STT/NLU/RAG/LLM/TTS), over the CloudFone WebSocket protocol the voice
worker already speaks natively (see cloudfone/protocol.py,
telephony/cloudfone.py's identity-passthrough adapter, api/routers/ws.py).

No new server-side code needed: this plays the role mod_audio_fork used to
play inside FreeSWITCH — RTP in, WS events out, WS events in, RTP out — but
as our own process instead of a C module inside a media server we can't fix.

RTP audio (both directions) is already G.711 μ-law @ 8kHz, matching
audio_frame's expected wire format exactly — no resampling/transcoding.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from typing import Any

import numpy as np
import websockets

from audio.codec import pcm_to_ulaw
from obs.tracing import new_traceparent
from sip.client import SipCall

logger = logging.getLogger(__name__)


async def bridge_call(
    call: SipCall,
    ws_url: str,
    script: dict[str, Any],
    campaign_id: str | None = None,
) -> None:
    """Run for the lifetime of one call. Returns when the worker ends the
    call (hangup/handoff) or the WS/SIP side closes."""
    session_id = str(uuid.uuid4())
    # Minted here, at the moment the call is answered, so one trace id spans
    # the whole call across every hop: softphone → voice worker → NestJS →
    # the call_sessions row → the trace in Grafana/Tempo.
    traceparent = new_traceparent()
    trace_id = traceparent.split("-")[1]
    logger.info("Call trace: session=%s trace_id=%s", session_id, trace_id)

    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(json.dumps({
            "event": "start",
            "session_id": session_id,
            "traceparent": traceparent,
            "campaign_id": campaign_id or script.get("campaign_id"),
            "script_version_id": script.get("id"),
            "direction": "inbound",
            "caller_number": call.caller_number,
            "caller_number_masked": None,
            "script": script,
        }))
        logger.info("CloudFone bridge: connected session=%s caller=%s", session_id, call.caller_number)

        to_worker = asyncio.create_task(_pump_rtp_to_ws(call, ws))
        from_worker = asyncio.create_task(_pump_ws_to_rtp(call, ws))

        done, pending = await asyncio.wait(
            {to_worker, from_worker}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None:
                logger.warning("CloudFone bridge: %s ended with %s", task.get_name(), exc)

    logger.info("CloudFone bridge: closed session=%s", session_id)


async def _pump_rtp_to_ws(call: SipCall, ws: websockets.WebSocketClientProtocol) -> None:
    """Caller's voice (RTP, from voip24h) -> audio_frame events -> worker."""
    while True:
        pcm = await call.rtp.read_pcm()
        samples = np.frombuffer(pcm, dtype=np.int16)
        ulaw = pcm_to_ulaw(samples)  # already bytes
        await ws.send(json.dumps({
            "event": "audio_frame",
            "data": base64.b64encode(ulaw).decode("ascii"),
        }))


async def _pump_ws_to_rtp(call: SipCall, ws: websockets.WebSocketClientProtocol) -> None:
    """AI's voice (from worker, over WS) -> RTP -> caller's phone."""
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        event = msg.get("event")
        if event == "audio_chunk":
            pcm = base64.b64decode(msg["data"])
            await call.rtp.write_pcm(pcm)
        elif event == "flush":
            call.flush_playback()
        elif event in ("hangup", "handoff", "error"):
            logger.info("CloudFone bridge: worker sent %s — ending bridge", event)
            return
