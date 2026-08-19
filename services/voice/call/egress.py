"""Egress — everything that turns text/beats into wire messages via the
telephony adapter (`_send` / `_send_beat` / `_send_audio` from the old
`ws.py`, unchanged), plus the synthesis-then-send helpers that every dialogue
path (FSM, RAG-assisted, Phase 3 answer injection, D1/D2 fallback speech)
shares: `stream_step` (FSM script-step beats), `say` (single-string
synth+send), and `emit_filler` (concurrent filler audio while the real
response is computed).

LLM-token-stream-to-TTS (`_tts_stream`) stays in `call/dialogue.py` — it's
specific to `ConversationEngine` output, not a generic egress primitive.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from fastapi import WebSocket

from call.events import AudioChunkPayload, BeatPayload
from telephony import TelephonyAdapter
from tts.chain import TTSChain
from tts.fillers import FillerSelector
from tts.text_normalizer import normalize as tts_normalize

logger = logging.getLogger(__name__)

_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")


class EgressSender:
    """One instance per call. Wraps `ws` + `adapter` so every other
    collaborator sends audio/beats without touching the WS or adapter
    directly."""

    def __init__(self, ws: WebSocket, adapter: TelephonyAdapter) -> None:
        self.ws = ws
        self.adapter = adapter

    async def send(self, payload: dict[str, Any]) -> None:
        """Encode an internal (CloudFone-shaped) event and send it.

        A provider may translate one internal event into several wire
        messages (e.g. Twilio chunks one audio_chunk into many 20ms `media`
        frames), or into none at all (events it has no equivalent for).
        """
        for msg in self.adapter.encode_outbound(payload):
            await self.ws.send_json(msg)

    async def send_beat(self, beat: BeatPayload) -> None:
        await self.send(beat.to_dict())

    async def send_audio(self, pcm_bytes: bytes, turn: int) -> None:
        chunk = AudioChunkPayload(data=base64.b64encode(pcm_bytes).decode(), turn=turn)
        await self.send(chunk.to_dict())

    async def say(
        self,
        text: str,
        turn: int,
        t_start: float,
        step_id: str,
        tts_chain: TTSChain | None,
        tts: object | None,
    ) -> None:
        """Synthesize and send a single text string (used by RAG answers,
        Phase 3 answer injection, and the D1/D2 fallback speech line)."""
        normalized = tts_normalize(text)
        beat = BeatPayload(
            text=text, pause_ms=500, turn=turn, step_id=step_id,
            ttfa_ms=round((time.perf_counter() - t_start) * 1000, 1),
        )
        await self.send_beat(beat)
        active_tts = tts_chain or tts
        if active_tts is None:
            return
        try:
            if tts_chain is not None:
                audio = await tts_chain.synthesize(normalized)
            else:
                audio = await tts.synthesize(normalized)  # type: ignore[union-attr]
            await self.send_audio(audio, turn)
        except Exception as tts_exc:
            logger.warning("TTS synthesis failed (beat-only fallback): %s", tts_exc)

    async def emit_filler(
        self,
        filler_text: str,
        filler_pcm: bytes | None,
        turn: int,
        t_start: float,
        step_id: str,
        tts_chain: TTSChain | None,
        tts: object | None,
    ) -> None:
        """Send a filler sound — pre-recorded audio when available, falls
        back to synthesis, falls back to a text-only beat."""
        if not filler_text and filler_pcm is None:
            return
        active_tts = tts_chain or tts
        if filler_pcm is not None:
            await self.send_audio(filler_pcm, turn)
        elif active_tts and filler_text:
            try:
                pcm = await active_tts.synthesize(filler_text)  # type: ignore[union-attr]
                await self.send_audio(pcm, turn)
            except Exception as exc:
                logger.warning("Filler synthesis failed: %s", exc)
        elif filler_text:
            beat = BeatPayload(
                text=filler_text, pause_ms=0, turn=turn, step_id=step_id,
                ttfa_ms=round((time.perf_counter() - t_start) * 1000, 1),
            )
            await self.send_beat(beat)

    async def stream_step(
        self,
        step: dict,
        slots: dict,
        no_match: int,
        turn: int,
        t_start: float,
        *,
        current_step_id: str,
        tts: object | None,
        tts_interrupt: asyncio.Event,
        on_tts_start: Callable[[], None],
        on_tts_end: Callable[[], None],
    ) -> None:
        """Stream one FSM script step's beats + audio (legacy `stream_step`
        path — script-authored beats, not LLM-generated text)."""
        on_tts_start()
        try:
            if tts:
                from tts.audio_stream import BeatsAudioStream  # noqa: PLC0415

                variant = _pick_variant(step, no_match)
                beats: list[dict] = variant.get("beats", [])

                _slots = slots or {}
                for beat_dict in beats:
                    raw_text = beat_dict.get("text", "")
                    text = _TEMPLATE_VAR.sub(lambda m: _slots.get(m.group(1), m.group(0)), raw_text)
                    if text.strip():
                        await self.send_beat(BeatPayload(
                            text=text, pause_ms=beat_dict.get("pause_ms", 0),
                            turn=turn, step_id=current_step_id,
                        ))

                if hasattr(tts, "stream_step"):
                    gen = await tts.stream_step(beats, slots, tts_interrupt)  # type: ignore[union-attr]
                else:
                    gen = BeatsAudioStream(tts, tts_interrupt).stream(beats, slots)
                first = True
                async for chunk in gen:
                    if first:
                        ttfa_ms = round((time.perf_counter() - t_start) * 1000, 1)
                        logger.info("TTFA: %.1f ms", ttfa_ms)
                        first = False
                    await self.send_audio(chunk, turn)
            else:
                from tts.streamer import stream_step_beats  # noqa: PLC0415

                async for beat in stream_step_beats(step, slots, no_match, turn, t_start):
                    if tts_interrupt.is_set():
                        break
                    await self.send_beat(beat)
        finally:
            on_tts_end()


def _pick_variant(step: dict, no_match_count: int) -> dict:
    if no_match_count > 0 and step.get("reprompt_variants"):
        reprompts: list[dict] = step["reprompt_variants"]
        idx = (no_match_count - 1) % len(reprompts)
        return reprompts[idx]
    variants: list[dict] = step.get("variants", [])
    return variants[0] if variants else {}
