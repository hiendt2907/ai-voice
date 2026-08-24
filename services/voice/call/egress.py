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
from starlette.websockets import WebSocketDisconnect, WebSocketState

from call.events import AudioChunkPayload, BeatPayload
from telephony import TelephonyAdapter
from tts.chain import TTSChain
from tts.text_normalizer import normalize as tts_normalize

logger = logging.getLogger(__name__)

_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")

# Thông điệp lỗi chính xác mà Starlette ném ra khi gọi send() sau khi một
# close message đã được gửi (xem starlette/websockets.py WebSocket.send()).
# Dùng so khớp CHÍNH XÁC chuỗi này — không bắt RuntimeError chung chung —
# để không nuốt nhầm một RuntimeError khác có nguyên nhân thật sự cần biết.
_WS_ALREADY_CLOSED_MSG = 'Cannot call "send" once a close message has been sent.'

# PCM handed to send_audio is always int16 @ 8kHz (see simulator/
# call_simulator.py's _PLAYBACK_SR) — used to convert bytes sent into an
# estimated client-side playback duration for the audio-position clock
# below (fixes the barge-in "overshoot" gap: TTS is considered active only
# until synthesis finishes on the server, but Piper/RemoteTTS can push a
# multi-second reply over the WS in a few hundred ms, so the client is
# still audibly playing long after the server thinks it's done talking).
_PLAYBACK_SAMPLE_RATE = 8000
_PLAYBACK_BYTES_PER_SAMPLE = 2


class EgressSender:
    """One instance per call. Wraps `ws` + `adapter` so every other
    collaborator sends audio/beats without touching the WS or adapter
    directly."""

    def __init__(self, ws: WebSocket, adapter: TelephonyAdapter) -> None:
        self.ws = ws
        self.adapter = adapter
        # Monotonic timestamp at which all audio handed to send_audio() so
        # far is expected to finish playing on the client. An audio-position
        # clock, not a wall-clock flag around synthesis — see module note.
        self._playback_deadline = 0.0

    @property
    def is_playing(self) -> bool:
        """True while the client is still expected to be playing audio we
        already sent (estimated from bytes sent, not synthesis state)."""
        return time.monotonic() < self._playback_deadline

    def reset_playback(self) -> None:
        """Call on barge-in flush: the client just dropped whatever audio it
        had queued, so estimated playback ends now regardless of how much
        we'd previously queued for it."""
        self._playback_deadline = time.monotonic()

    async def send(self, payload: dict[str, Any]) -> bool:
        """Encode an internal (CloudFone-shaped) event and send it.

        A provider may translate one internal event into several wire
        messages (e.g. Twilio chunks one audio_chunk into many 20ms `media`
        frames), or into none at all (events it has no equivalent for).
        `encode_outbound` may also return raw `bytes` items — a provider
        whose transport expects binary WS frames for audio (e.g. FreeSWITCH's
        mod_audio_fork in bidirectional *streaming* mode) instead of
        JSON-wrapped base64.

        Returns True if the payload was actually put on the wire, False if
        it was silently dropped because the WebSocket is already closed
        (khách đã cúp máy). Đây là ca bình thường cuối cuộc gọi — không phải
        lỗi hệ thống — nên không ném exception lên caller (FSM/RAG/handoff
        đều gọi send() mà không bọc try/except quanh mỗi lần gọi).

        Kiểm tra `application_state` TRƯỚC khi gửi là cách Starlette hỗ trợ
        chính thức để biết kết nối còn sống hay không (public attribute,
        không phải suy đoán từ nội dung exception). Vẫn còn một khe hở đua
        (race) rất hẹp giữa lúc kiểm tra và lúc `_send` ASGI thật sự chạy —
        ví dụ task đọc inbound đóng kết nối đúng lúc task này đang giữa
        vòng lặp gửi nhiều message cho cùng một payload — nên phần catch
        bên dưới là lưới đỡ cho đúng khe hở đó, so khớp CHÍNH XÁC thông
        điệp lỗi của Starlette thay vì bắt RuntimeError chung chung.
        """
        ws_state = getattr(self.ws, "application_state", WebSocketState.CONNECTED)
        if ws_state != WebSocketState.CONNECTED:
            logger.debug(
                "EgressSender.send: bỏ qua gửi vì WebSocket đã đóng "
                "(application_state=%s, event=%s)",
                ws_state, payload.get("event"),
            )
            return False

        for msg in self.adapter.encode_outbound(payload):
            try:
                if isinstance(msg, bytes):
                    await self.ws.send_bytes(msg)
                else:
                    await self.ws.send_json(msg)
            except RuntimeError as exc:
                if str(exc) != _WS_ALREADY_CLOSED_MSG:
                    raise
                # Khách cúp máy đúng giữa lúc ta đang gửi (khe hở đua giữa
                # kiểm tra state ở trên và lệnh gửi thật) — bỏ qua phần còn
                # lại của payload này, không coi là lỗi hệ thống.
                logger.debug(
                    "EgressSender.send: WebSocket đóng ngay giữa lúc gửi "
                    "(event=%s) — bỏ qua phần còn lại",
                    payload.get("event"),
                )
                return False
            except WebSocketDisconnect:
                # Cùng khe hở đua như trên nhưng lộ ra ở tầng ASGI thấp hơn:
                # uvicorn phát hiện ClientDisconnected ngay trong send() rồi
                # Starlette bọc lại thành WebSocketDisconnect thay vì
                # RuntimeError — bắt được bằng thực nghiệm thật (simulator
                # cúp máy giữa lúc _fsm_rag_intercept đang nói), không phải
                # suy đoán. Không so khớp message vì đây đã là kiểu ngoại lệ
                # cụ thể, tự thân nó đã nghĩa là "socket đóng rồi".
                logger.debug(
                    "EgressSender.send: WebSocketDisconnect giữa lúc gửi "
                    "(event=%s) — bỏ qua phần còn lại",
                    payload.get("event"),
                )
                return False
        return True

    async def send_beat(self, beat: BeatPayload) -> bool:
        return await self.send(beat.to_dict())

    async def send_audio(self, pcm_bytes: bytes, turn: int) -> bool:
        chunk = AudioChunkPayload(data=base64.b64encode(pcm_bytes).decode(), turn=turn)
        sent = await self.send(chunk.to_dict())
        if sent:
            # Không cộng dồn playback-deadline cho audio chưa thực sự lên
            # dây — khách đã cúp máy thì không còn ai để "còn đang nghe".
            duration_s = len(pcm_bytes) / (_PLAYBACK_SAMPLE_RATE * _PLAYBACK_BYTES_PER_SAMPLE)
            now = time.monotonic()
            self._playback_deadline = max(now, self._playback_deadline) + duration_s
        return sent

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
        beat_sent = await self.send_beat(beat)
        if not beat_sent:
            # WebSocket đã đóng (khách cúp máy) — không còn ai nghe, khỏi
            # tốn công tổng hợp giọng nói cho một kết nối đã chết.
            return
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
            await self.send_audio(filler_pcm, turn)  # gửi được hay không không ảnh hưởng gì thêm ở đây
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
                ws_closed = False
                for beat_dict in beats:
                    raw_text = beat_dict.get("text", "")
                    text = _TEMPLATE_VAR.sub(lambda m: _slots.get(m.group(1), m.group(0)), raw_text)
                    if not text.strip():
                        continue
                    beat_sent = await self.send_beat(BeatPayload(
                        text=text, pause_ms=beat_dict.get("pause_ms", 0),
                        turn=turn, step_id=current_step_id,
                    ))
                    if not beat_sent:
                        # Khách cúp máy giữa lượt — các beat còn lại của
                        # CÙNG turn này sẽ gặp đúng tình trạng đã đóng,
                        # dừng sớm thay vì lặp lại việc gửi vô ích.
                        ws_closed = True
                        break

                if ws_closed:
                    return
                if hasattr(tts, "stream_step"):
                    gen = await tts.stream_step(beats, slots, tts_interrupt)  # type: ignore[union-attr]
                else:
                    gen = BeatsAudioStream(tts, tts_interrupt).stream(beats, slots)
                first = True
                chunks = 0
                audio_bytes = 0
                ws_closed_mid_audio = False
                try:
                    async for chunk in gen:
                        if first:
                            ttfa_ms = round((time.perf_counter() - t_start) * 1000, 1)
                            logger.info("TTFA: %.1f ms", ttfa_ms)
                            first = False
                        chunks += 1
                        audio_bytes += len(chunk)
                        if not await self.send_audio(chunk, turn):
                            # Khách cúp máy giữa lúc đang phát audio — không
                            # còn ai để nghe phần còn lại. Dừng kéo thêm
                            # chunk từ TTS (đóng generator để giải phóng tài
                            # nguyên tổng hợp giọng nói đang chạy dở) thay vì
                            # tiếp tục gửi vô ích và lặp lại đúng tình trạng
                            # đã đóng cho mỗi chunk còn lại.
                            ws_closed_mid_audio = True
                            await gen.aclose()
                            break
                finally:
                    # Logged unconditionally (including on interrupt/error):
                    # "TTFA printed, then silence" is ambiguous without it —
                    # it can't distinguish a full reply from a stream that
                    # died after its first frame.
                    logger.info(
                        "TTS stream done: turn=%s chunks=%d %.2fs audio in %.0f ms%s",
                        turn, chunks,
                        audio_bytes / (_PLAYBACK_SAMPLE_RATE * _PLAYBACK_BYTES_PER_SAMPLE),
                        (time.perf_counter() - t_start) * 1000,
                        " (interrupted)" if tts_interrupt.is_set()
                        else " (ws đã đóng)" if ws_closed_mid_audio else "",
                    )
            else:
                from tts.streamer import stream_step_beats  # noqa: PLC0415

                async for beat in stream_step_beats(step, slots, no_match, turn, t_start):
                    if tts_interrupt.is_set():
                        break
                    if not await self.send_beat(beat):
                        # Cùng lý do như nhánh tts ở trên: khách đã cúp máy,
                        # dừng sớm thay vì lặp lại lỗi cho từng beat còn lại.
                        break
        finally:
            on_tts_end()


def _pick_variant(step: dict, no_match_count: int) -> dict:
    if no_match_count > 0 and step.get("reprompt_variants"):
        reprompts: list[dict] = step["reprompt_variants"]
        idx = (no_match_count - 1) % len(reprompts)
        return reprompts[idx]
    variants: list[dict] = step.get("variants", [])
    return variants[0] if variants else {}
