"""Unit tests for call.media.MediaRouter (audio feed + barge-in detection)."""

from __future__ import annotations

import asyncio
import base64
import contextlib

import numpy as np
import pytest

from audio.codec import pcm_to_ulaw
from call.media import MediaRouter
from stt.streaming_remote_stt import StreamingRemoteSTT, StreamingRemoteSTTError
from stt.vad import VADDetector


def _frame_b64(amplitude: int, n_samples: int = 160) -> str:
    pcm = (np.ones(n_samples, dtype=np.int16) * amplitude)
    return base64.b64encode(pcm_to_ulaw(pcm)).decode()


# ── no-pipeline fallback (mirrors the pre-refactor RMS branch exactly) ──────


def test_feed_without_pipeline_loud_frame_is_barge_in_when_tts_active():
    router = MediaRouter(session_id="s1")

    is_barge_in = router.feed(_frame_b64(amplitude=8000), tts_active=True)

    assert is_barge_in is True


def test_feed_without_pipeline_loud_frame_not_barge_in_when_tts_inactive():
    router = MediaRouter(session_id="s1")

    is_barge_in = router.feed(_frame_b64(amplitude=8000), tts_active=False)

    assert is_barge_in is False


def test_feed_without_pipeline_silent_frame_is_not_barge_in():
    router = MediaRouter(session_id="s1")

    is_barge_in = router.feed(_frame_b64(amplitude=0), tts_active=True)

    assert is_barge_in is False


def test_on_tts_start_end_are_noop_without_a_pipeline():
    router = MediaRouter(session_id="s1")

    router.on_tts_start()  # must not raise
    router.on_tts_end()  # must not raise


def test_is_speech_active_false_without_a_pipeline():
    router = MediaRouter(session_id="s1")

    assert router.is_speech_active is False


def test_stop_without_a_pipeline_is_a_noop():
    router = MediaRouter(session_id="s1")

    router.stop()  # must not raise


# ── with a fake pipeline ────────────────────────────────────────────────────


class _FakeVAD:
    def __init__(self) -> None:
        self.started = 0
        self.ended = 0

    def on_tts_start(self) -> None:
        self.started += 1

    def on_tts_end(self) -> None:
        self.ended += 1


class _FakePipeline:
    def __init__(self, speech_active: bool) -> None:
        self._vad = _FakeVAD()
        self.is_speech_active = speech_active
        self.fed: list[bytes] = []
        self.stopped = False

    def feed(self, data: bytes) -> None:
        self.fed.append(data)

    def stop(self) -> None:
        self.stopped = True


def test_feed_with_pipeline_delegates_and_reports_speech_active():
    router = MediaRouter(session_id="s1")
    router.pipeline = _FakePipeline(speech_active=True)  # type: ignore[assignment]

    is_barge_in = router.feed(_frame_b64(amplitude=100), tts_active=True)

    assert is_barge_in is True
    assert len(router.pipeline.fed) == 1  # type: ignore[union-attr]


def test_feed_with_pipeline_not_barge_in_when_tts_inactive():
    router = MediaRouter(session_id="s1")
    router.pipeline = _FakePipeline(speech_active=True)  # type: ignore[assignment]

    is_barge_in = router.feed(_frame_b64(amplitude=100), tts_active=False)

    assert is_barge_in is False


def test_on_tts_start_end_delegate_to_pipeline_vad():
    router = MediaRouter(session_id="s1")
    fake = _FakePipeline(speech_active=False)
    router.pipeline = fake  # type: ignore[assignment]

    router.on_tts_start()
    router.on_tts_end()

    assert fake._vad.started == 1
    assert fake._vad.ended == 1


def test_stop_delegates_to_pipeline():
    router = MediaRouter(session_id="s1")
    fake = _FakePipeline(speech_active=False)
    router.pipeline = fake  # type: ignore[assignment]

    router.stop()

    assert fake.stopped is True


@pytest.mark.asyncio
async def test_start_returns_none_when_no_stt_configured():
    router = MediaRouter(session_id="s1")

    async def _on_transcript(text: str, emotion: str | None) -> None:
        pass

    async def _on_failure() -> None:
        pass

    task = router.start(None, _on_transcript, _on_failure)

    assert task is None
    assert router.pipeline is None


# ── Phase 2: streaming STT path (StreamingRemoteSTT, feature-flagged) ──────


class _FakeStreamingSTT(StreamingRemoteSTT):
    """Stands in for a real WS connection — no networking involved."""

    def __init__(
        self,
        *,
        fail_connect: bool = False,
        fail_listen: bool = False,
        final_text: str | None = "dạ vâng",
        block_forever: bool = False,
    ) -> None:
        super().__init__("http://fake", token="t")
        self.fail_connect = fail_connect
        self.fail_listen = fail_listen
        self.final_text = final_text
        self.block_forever = block_forever
        self.started_turns: list[str] = []
        self.sent_audio: list[bytes] = []
        self.ended_turns = 0
        self.closed = False

    async def connect(self) -> None:
        if self.fail_connect:
            raise StreamingRemoteSTTError("boom")

    async def close(self) -> None:
        self.closed = True

    async def start_turn(self, turn_id: str) -> None:
        self.started_turns.append(turn_id)

    async def send_audio(self, pcm_bytes: bytes) -> None:
        self.sent_audio.append(pcm_bytes)

    async def end_turn(self) -> None:
        self.ended_turns += 1

    async def listen(self, on_partial=None, on_final=None, on_endpoint=None) -> None:  # type: ignore[override]
        if self.fail_listen:
            raise StreamingRemoteSTTError("connection lost")
        if self.final_text is not None and on_final is not None:
            await on_final("1", self.final_text, 0.5)
        if self.block_forever:
            await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_start_detects_streaming_stt_instance():
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(block_forever=True)

    async def _on_transcript(text, emotion):
        pass

    async def _on_failure():
        pass

    task = router.start(fake_stt, _on_transcript, _on_failure)

    assert task is not None
    assert router.pipeline is None  # streaming path never builds an AudioPipeline
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_streaming_final_transcript_reaches_on_transcript_and_closes():
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(final_text="chào bác sĩ")
    received: list[tuple[str, str | None]] = []

    async def _on_transcript(text, emotion):
        received.append((text, emotion))

    async def _on_failure():
        pytest.fail("should not fall back on a clean final")

    task = router.start(fake_stt, _on_transcript, _on_failure, turn_id_provider=lambda: "1")
    await asyncio.wait_for(task, timeout=2.0)

    assert received == [("chào bác sĩ", None)]
    assert fake_stt.closed is True


@pytest.mark.asyncio
async def test_streaming_connect_failure_degrades_to_http_never_hangs_up():
    """D2: a streaming WS connect failure must degrade to the HTTP one-shot
    RemoteSTT for the rest of the call, not hang up (`on_pipeline_failure`
    must NOT be called just because the streaming tier is unreachable)."""
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(fail_connect=True)
    hangup = asyncio.Event()

    async def _on_transcript(text, emotion):
        pass

    async def _on_failure():
        hangup.set()

    task = router.start(fake_stt, _on_transcript, _on_failure)
    await asyncio.wait_for(task, timeout=2.0)

    assert not hangup.is_set()  # must NOT hang up the call
    assert router.pipeline is not None  # degraded to the plain AudioPipeline/HTTP path
    assert router._streaming_stt is None  # noqa: SLF001 — switched off streaming


@pytest.mark.asyncio
async def test_streaming_listen_disconnect_degrades_to_http_never_hangs_up():
    """D2: a mid-call WS drop must degrade to HTTP RemoteSTT for the
    remaining turns instead of ending the call — matches the historical
    HTTP-one-shot behaviour where a transport failure never killed the
    whole call outright."""
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(fail_listen=True, final_text=None)
    hangup = asyncio.Event()

    async def _on_transcript(text, emotion):
        pass

    async def _on_failure():
        hangup.set()

    task = router.start(fake_stt, _on_transcript, _on_failure)
    await asyncio.wait_for(task, timeout=2.0)

    assert not hangup.is_set()  # must NOT hang up the call
    assert fake_stt.closed is True
    assert router.pipeline is not None  # degraded to the plain AudioPipeline/HTTP path
    assert router._streaming_stt is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_streaming_degrade_continues_serving_audio_via_http_pipeline():
    """After degrading, subsequent feed() calls must route to the fallback
    AudioPipeline (HTTP) rather than being silently dropped — the call keeps
    working for its remaining turns."""
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(fail_listen=True, final_text=None)

    async def _on_transcript(text, emotion):
        pass

    async def _on_failure():
        pytest.fail("must not hang up after degrading")

    task = router.start(fake_stt, _on_transcript, _on_failure)
    await asyncio.wait_for(task, timeout=2.0)
    assert router.pipeline is not None

    # feed() after degrade must go through the AudioPipeline branch, not the
    # (now-cleared) streaming branch or the no-pipeline RMS fallback.
    router.feed(_frame_b64(amplitude=8000), tts_active=True)
    await asyncio.sleep(0.05)  # let the background pipeline drain task consume the frame

    assert router.pipeline.is_speech_active is True


@pytest.mark.asyncio
async def test_streaming_pipeline_failure_after_degrade_still_hangs_up():
    """If the HTTP fallback pipeline ALSO fails, that's a genuinely
    unrecoverable state — falling back to hang-up is still correct there."""
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(fail_listen=True, final_text=None)
    hangup = asyncio.Event()

    async def _on_transcript(text, emotion):
        pass

    async def _on_failure():
        hangup.set()

    task = router.start(fake_stt, _on_transcript, _on_failure)
    await asyncio.wait_for(task, timeout=2.0)
    assert router.pipeline is not None

    class _BoomSTT:
        async def transcribe_pcm(self, pcm_bytes, sample_rate=8000):
            raise RuntimeError("HTTP inference server also unreachable")

    router.pipeline._stt = _BoomSTT()  # noqa: SLF001
    router.pipeline._stt_is_async = True  # noqa: SLF001
    router.feed(_frame_b64(amplitude=8000), tts_active=False)  # buffer some speech
    router.stop()  # flushes the buffer unconditionally -> _BoomSTT raises -> hang up

    await asyncio.wait_for(hangup.wait(), timeout=2.0)


def test_feed_streaming_routes_frame_and_reports_speech_active():
    router = MediaRouter(session_id="s1")
    router._streaming_stt = _FakeStreamingSTT(block_forever=True)  # noqa: SLF001
    router._streaming_vad = VADDetector(sample_rate=8000)  # noqa: SLF001
    router._streaming_queue = asyncio.Queue()  # noqa: SLF001

    is_barge_in = router.feed(_frame_b64(amplitude=8000), tts_active=True)

    assert is_barge_in is True
    assert router._streaming_queue.qsize() == 1  # noqa: SLF001


@pytest.mark.asyncio
async def test_feed_streaming_send_loop_opens_turn_and_forwards_audio():
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(final_text=None, block_forever=True)

    async def _on_transcript(text, emotion):
        pass

    async def _on_failure():
        pass

    task = router.start(fake_stt, _on_transcript, _on_failure, turn_id_provider=lambda: "9")
    router.feed(_frame_b64(amplitude=8000), tts_active=False)
    await asyncio.sleep(0.05)  # let the background send loop drain the queue

    assert fake_stt.started_turns == ["9"]
    assert fake_stt.sent_audio

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_feed_streaming_preroll_flushed_when_turn_opens():
    """Fix for lost first words: audio buffered before VAD first triggers
    speech must be sent to the turn too (prepended), not dropped."""
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(final_text=None, block_forever=True)

    async def _on_transcript(text, emotion):
        pass

    async def _on_failure():
        pass

    task = router.start(fake_stt, _on_transcript, _on_failure, turn_id_provider=lambda: "5")

    # Three frames of pre-speech silence, then the loud frame VAD actually
    # triggers on — mirrors a caller taking a breath before "Dạ, ...".
    for _ in range(3):
        router.feed(_frame_b64(amplitude=0), tts_active=False)
    router.feed(_frame_b64(amplitude=8000), tts_active=False)
    await asyncio.sleep(0.05)  # let the background send loop drain the queue

    assert fake_stt.started_turns == ["5"]
    # 3 buffered pre-roll frames + the triggering frame itself, all forwarded.
    assert len(fake_stt.sent_audio) == 4

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_feed_streaming_preroll_buffer_is_bounded():
    """The pre-roll buffer must not grow unbounded during a long silence —
    only the last ~300ms should be kept and flushed once speech starts."""
    router = MediaRouter(session_id="s1")
    fake_stt = _FakeStreamingSTT(final_text=None, block_forever=True)

    async def _on_transcript(text, emotion):
        pass

    async def _on_failure():
        pass

    task = router.start(fake_stt, _on_transcript, _on_failure, turn_id_provider=lambda: "6")

    # 30 x 20ms silent frames = 600ms of silence, well over the 300ms cap.
    for _ in range(30):
        router.feed(_frame_b64(amplitude=0), tts_active=False)
    router.feed(_frame_b64(amplitude=8000), tts_active=False)
    await asyncio.sleep(0.05)

    assert fake_stt.started_turns == ["6"]
    # Bounded to ~300ms of pre-roll (15 x 20ms frames) + the triggering frame.
    assert len(fake_stt.sent_audio) <= 16
    assert len(fake_stt.sent_audio) > 1  # still more than just the trigger frame

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def test_stop_streaming_enqueues_sentinel():
    router = MediaRouter(session_id="s1")
    router._streaming_queue = asyncio.Queue()  # noqa: SLF001

    router.stop()

    assert router._streaming_queue.get_nowait() is None  # noqa: SLF001


def test_on_tts_start_end_delegate_to_streaming_vad():
    router = MediaRouter(session_id="s1")
    router._streaming_vad = VADDetector(sample_rate=8000)  # noqa: SLF001

    router.on_tts_start()
    assert router._streaming_vad.is_half_duplex_suppressed is True  # noqa: SLF001

    router.on_tts_end()
    assert router._streaming_vad.is_half_duplex_suppressed is False  # noqa: SLF001


def test_is_speech_active_delegates_to_streaming_vad_when_present():
    router = MediaRouter(session_id="s1")
    router._streaming_vad = VADDetector(sample_rate=8000)  # noqa: SLF001

    assert router.is_speech_active is False


# ── flush (barge-in: tell the provider to drop in-flight playback) ────────


class _FakeEgress:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_flush_sends_flush_event_through_egress():
    egress = _FakeEgress()
    router = MediaRouter(session_id="s1", egress=egress)  # type: ignore[arg-type]

    await router.flush(turn=3)

    assert egress.sent == [{"event": "flush", "turn": 3}]


@pytest.mark.asyncio
async def test_flush_without_egress_is_a_noop():
    router = MediaRouter(session_id="s1")

    await router.flush(turn=1)  # must not raise
