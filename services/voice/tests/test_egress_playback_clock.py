"""Real-audio test for the barge-in "overshoot" fix (B1.3 in the streaming
call-test plan): `EgressSender` tracks an audio-position playback clock
(`is_playing`/`reset_playback`) instead of gating barge-in on a boolean that
flips False the instant server-side SYNTHESIS finishes.

Uses the real vi_VN-vais1000-medium Piper model (no mocks) — Piper is fast
enough locally that a 3-sentence reply's synthesis wall time is well under
the audio's own playback duration, which is exactly the gap that used to
make the server think TTS was "done" while the client was still audibly
playing several seconds of queued audio.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest

from call.egress import EgressSender
from tts.piper_tts import PiperTTS

_MODEL_PATH = (
    Path(__file__).parent.parent / "models" / "piper" / "vi_VN-vais1000-medium.onnx"
)

pytestmark = pytest.mark.skipif(
    not _MODEL_PATH.exists(),
    reason="Piper model weights not present in this environment (local-inference extra)",
)


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_json(self, msg: dict[str, Any]) -> None:
        self.sent.append(msg)


class _IdentityAdapter:
    def encode_outbound(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [payload]

    async def on_call_end(self, reason: str, session_id: str) -> None:
        pass


_LONG_REPLY = (
    "Dạ, hiện tại buổi sáng ngày thứ Sáu phòng khám vẫn còn trống lịch ạ. "
    "Em đặt luôn cho mình nhé? Anh chị vui lòng giữ máy trong giây lát ạ. "
    "Nếu cần đổi giờ khác thì mình báo em ngay bây giờ luôn nhé ạ."
)


async def test_is_playing_stays_true_right_after_fast_synthesis_completes():
    """The core overshoot bug: with the OLD design, TurnOrchestrator.tts_active
    (and VADDetector's on_tts_end()) flipped the instant this coroutine
    returned — i.e. the instant SYNTHESIS finished. For a fast local engine
    that can push several seconds of audio in a few hundred ms, that leaves
    the client still audibly playing while the server already thinks it's
    done. `is_playing` must stay True through that tail."""
    ws = _FakeWS()
    egress = EgressSender(ws, _IdentityAdapter())  # type: ignore[arg-type]
    tts = PiperTTS()
    step = {"variants": [{"beats": [{"text": _LONG_REPLY, "pause_after": "none"}]}]}
    interrupt = asyncio.Event()

    t0 = time.monotonic()
    await egress.stream_step(
        step, {}, 0, turn=1, t_start=t0,
        current_step_id="s1", tts=tts, tts_interrupt=interrupt,
        on_tts_start=lambda: None, on_tts_end=lambda: None,
    )
    synth_wall_s = time.monotonic() - t0

    audio_chunks = [m for m in ws.sent if m.get("event") == "audio_chunk"]
    assert audio_chunks, "expected at least one audio_chunk to have been sent"

    assert egress.is_playing, (
        f"is_playing should still be True immediately after synthesis "
        f"(took {synth_wall_s * 1000:.0f}ms) for a 3-sentence reply — this is "
        "exactly the overshoot window where the old tts_active boolean was wrong"
    )


async def test_reset_playback_ends_playback_immediately_for_barge_in():
    ws = _FakeWS()
    egress = EgressSender(ws, _IdentityAdapter())  # type: ignore[arg-type]
    tts = PiperTTS()
    step = {"variants": [{"beats": [{"text": _LONG_REPLY, "pause_after": "none"}]}]}
    interrupt = asyncio.Event()

    await egress.stream_step(
        step, {}, 0, turn=1, t_start=time.monotonic(),
        current_step_id="s1", tts=tts, tts_interrupt=interrupt,
        on_tts_start=lambda: None, on_tts_end=lambda: None,
    )
    assert egress.is_playing  # sanity: still in the overshoot window

    egress.reset_playback()  # what MediaRouter.flush() calls on barge-in

    assert not egress.is_playing


async def test_is_playing_false_before_any_audio_sent():
    ws = _FakeWS()
    egress = EgressSender(ws, _IdentityAdapter())  # type: ignore[arg-type]
    assert not egress.is_playing
