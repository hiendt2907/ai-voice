"""FreeSWITCH (mod_audio_fork) adapter — the voip24h SIP trunk integration.

voip24h's REST API (`POST /v3/call/dial`) rings a SIP extension first and
only bridges to the outbound phone number once that extension answers —
there is no WebSocket/RTP hand-off exposed to a third party. FreeSWITCH
plays that extension (registers as a real SIP UA, see
`deploy/freeswitch/`), and `mod_audio_fork` forks the bridged call's PCM
audio out to this adapter's WS connection, and plays back whatever this
adapter sends it — the same shape as CloudFone's own WS protocol, just
sitting on top of SIP/RTP instead of a native web socket from the start.

Wire shape (see https://github.com/byteroycai/mod_audio_fork):
  - Inbound: ONE JSON text frame at connect (the `metadata` argument our
    own `deploy/freeswitch/templates/voip24h_bridge.lua.tpl` passes to
    `uuid_audio_fork ... start`), then ongoing BINARY frames of linear
    16-bit PCM @ 8kHz mono (caller audio). Requires api/routers/ws.py's
    receive loop to accept bytes frames, not just JSON text ones.
  - Outbound: JSON text frames only (`playAudio` / `killAudio` /
    `disconnect`) — FreeSWITCH plays the audio itself; we never write to
    the socket in binary.

CloudFone's `audio_frame`/`audio_chunk` events carry μ-law (the pipeline's
`call/media.py:MediaRouter.feed()` always base64-decodes then
`ulaw_to_pcm()`s), but mod_audio_fork speaks linear PCM — so this adapter
converts PCM→μ-law on the way in. Outbound stays linear PCM (matches
`call/egress.py:EgressSender.send_audio()`'s own 8kHz int16 format
exactly), just re-wrapped as a `playAudio` JSON message instead of
CloudFone's `audio_chunk`.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import numpy as np

from audio.codec import pcm_to_ulaw
from cloudfone.protocol import InboundEvent, OutboundEvent

logger = logging.getLogger(__name__)


class FreeSwitchAdapter:
    name = "freeswitch"

    def normalize_inbound(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """The one JSON text frame mod_audio_fork sends is the metadata our
        own Lua script supplied to `uuid_audio_fork start` — treat it as the
        internal "start" event. `script`/`campaign_id` are intentionally
        absent here (a single command-line-style metadata string can't
        reasonably carry a full script tree) — `api/routers/ws.py`'s
        `call_ws()` loads the script itself from the `script_id` query
        param when this adapter is selected, the same way the simulator
        loads scripts from `scripts/examples/`, not from a live orchestrator."""
        return {
            "event": InboundEvent.START,
            "session_id": raw.get("callId", ""),
            "campaign_id": None,
            "script_version_id": None,
            "direction": raw.get("direction", "outbound"),
            "caller_number": raw.get("callerIdNumber"),
            "caller_number_masked": None,
        }

    def normalize_inbound_binary(self, data: bytes) -> dict[str, Any] | None:
        """mod_audio_fork's linear-PCM binary audio frame → an internal
        `audio_frame` event carrying base64 μ-law, matching what
        `call/media.py:MediaRouter.feed()` already expects from CloudFone."""
        if not data:
            return None
        pcm = np.frombuffer(data, dtype=np.int16)
        ulaw_bytes = pcm_to_ulaw(pcm)
        return {
            "event": InboundEvent.AUDIO_FRAME,
            "data": base64.b64encode(ulaw_bytes).decode(),
        }

    def encode_outbound(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        event = payload.get("event")
        if event == OutboundEvent.AUDIO_CHUNK:
            pcm_b64 = payload.get("data", "")
            if not pcm_b64:
                return []
            return [{
                "type": "playAudio",
                "data": {
                    "audioContentType": "raw",
                    "sampleRate": 8000,
                    "audioContent": pcm_b64,
                },
            }]
        if event == OutboundEvent.FLUSH:
            return [{"type": "killAudio"}]
        if event == OutboundEvent.HANGUP:
            return [{"type": "disconnect"}]
        # beat / handoff / error have no mod_audio_fork wire equivalent —
        # FreeSWITCH plays audio itself, it has no text-beat display channel.
        return []

    async def on_call_end(self, reason: str, session_id: str) -> None:
        """No REST call needed on this leg — the far end of the bridge
        (voip24h's PSTN leg) tears down on its own when this SIP channel
        hangs up; FreeSWITCH handles that natively."""
