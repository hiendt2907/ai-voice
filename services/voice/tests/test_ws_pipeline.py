"""Tests for Sprint 4: protocol types, async executor, streamer."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from cloudfone.protocol import (
    AudioChunkPayload,
    BeatPayload,
    HangupPayload,
    HandoffPayload,
    InboundEvent,
    OutboundEvent,
    QuestionAnsweredMessage,
    StartMessage,
    UtteranceMessage,
)
from runtime.executor import _process_with_match, async_process_turn, create_session
from runtime.intent_matcher import MatchResult
from runtime.session import SessionState


# ---------------------------------------------------------------------------
# Protocol types
# ---------------------------------------------------------------------------

MINIMAL_SCRIPT = {
    "id": "test-script",
    "entry_step": "greeting",
    "steps": [
        {
            "id": "greeting",
            "type": "speak_listen",
            "variants": [{"id": "v1", "beats": [{"text": "Xin chào", "pause_after": "turn"}]}],
            "reprompt_variants": [{"id": "r1", "beats": [{"text": "R1", "pause_after": "turn"}]}],
            "transitions": [{"when": "intent == 'book'", "goto": "farewell"}],
            "fallback_goto": "farewell",
            "max_no_match": 2,
        },
        {
            "id": "farewell",
            "type": "speak",
            "variants": [{"id": "v1", "beats": [{"text": "Tạm biệt.", "pause_after": "long"}]}],
        },
    ],
    "intents": [{"intent": "book", "examples": [{"text": "đặt lịch"}]}],
}


def test_start_message_from_dict():
    d = {
        "event": "start",
        "session_id": "abc",
        "campaign_id": "c1",
        "script_version_id": "v1",
        "direction": "inbound",
        "caller_number": "0901234567",
        "caller_number_masked": "090***4567",
    }
    msg = StartMessage.from_dict(d)
    assert msg.session_id == "abc"
    assert msg.campaign_id == "c1"
    assert msg.caller_number_masked == "090***4567"


def test_utterance_message_from_dict():
    msg = UtteranceMessage.from_dict({"text": "đặt lịch", "confidence": 0.9})
    assert msg.text == "đặt lịch"
    assert msg.confidence == pytest.approx(0.9)


def test_beat_payload_to_dict():
    beat = BeatPayload(text="Xin chào", pause_ms=500, turn=1, step_id="greeting", ttfa_ms=123.4)
    d = beat.to_dict()
    assert d["event"] == OutboundEvent.BEAT
    assert d["text"] == "Xin chào"
    assert d["ttfa_ms"] == 123.4


def test_beat_payload_no_ttfa():
    beat = BeatPayload(text="Hi", pause_ms=0, turn=0, step_id="s1")
    d = beat.to_dict()
    assert "ttfa_ms" not in d


def test_hangup_payload():
    p = HangupPayload(step_id="farewell")
    d = p.to_dict()
    assert d["event"] == OutboundEvent.HANGUP
    assert d["step_id"] == "farewell"


def test_handoff_payload():
    p = HandoffPayload(reason="escalate", step_id="handoff_step")
    d = p.to_dict()
    assert d["event"] == OutboundEvent.HANDOFF
    assert d["reason"] == "escalate"


def test_audio_chunk_payload():
    import base64  # noqa: PLC0415

    data = base64.b64encode(b"\x00\x01\x02").decode()
    chunk = AudioChunkPayload(data=data, turn=2)
    d = chunk.to_dict()
    assert d["event"] == OutboundEvent.AUDIO_CHUNK
    assert d["turn"] == 2


def test_question_answered_message():
    msg = QuestionAnsweredMessage.from_dict({"question_id": "q1", "answer": "350.000đ"})
    assert msg.question_id == "q1"
    assert msg.answer == "350.000đ"


def test_inbound_event_values():
    assert InboundEvent.START == "start"
    assert InboundEvent.AUDIO_FRAME == "audio_frame"
    assert InboundEvent.QUESTION_ANSWERED == "question_answered"


# ---------------------------------------------------------------------------
# _process_with_match tests
# ---------------------------------------------------------------------------


def test_process_with_match_intent_fires_transition():
    state = create_session(MINIMAL_SCRIPT)
    match = MatchResult(intent="book", slots={}, confidence=0.9)
    result = _process_with_match(state, MINIMAL_SCRIPT, "đặt lịch", match)
    assert result.intent == "book"
    assert result.next_step_id == "farewell"
    assert result.is_completed is False


def test_process_with_match_no_intent():
    state = create_session(MINIMAL_SCRIPT)
    match = MatchResult(intent=None, slots={}, confidence=0.0)
    result = _process_with_match(state, MINIMAL_SCRIPT, "blah", match)
    assert result.intent is None
    assert result.next_step_id is None  # still in reprompt budget


def test_process_with_match_unknown_step():
    state = create_session(MINIMAL_SCRIPT).with_step("nonexistent")
    match = MatchResult(intent=None, slots={}, confidence=0.0)
    result = _process_with_match(state, MINIMAL_SCRIPT, None, match)
    assert result.is_completed is True


def test_process_with_match_terminal_step():
    state = create_session(MINIMAL_SCRIPT).with_step("farewell")
    match = MatchResult(intent=None, slots={}, confidence=0.0)
    result = _process_with_match(state, MINIMAL_SCRIPT, None, match)
    assert result.is_completed is True
    assert "Tạm biệt" in result.agent_text


# ---------------------------------------------------------------------------
# async_process_turn tests
# ---------------------------------------------------------------------------


async def test_async_process_turn_no_nlu():
    """With nlu=None, falls back to sync process_turn."""
    state = create_session(MINIMAL_SCRIPT)
    result = await async_process_turn(state, MINIMAL_SCRIPT, "đặt lịch", nlu=None)
    assert result.intent == "book"
    assert result.next_step_id == "farewell"


async def test_async_process_turn_with_nlu_success():
    """With working NLU, uses LLM result."""
    import json  # noqa: PLC0415
    from llm.nlu import LLMNLUClassifier  # noqa: PLC0415

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(return_value=json.dumps({
        "intent": "book",
        "slots": {},
        "confidence": 0.95,
        "is_out_of_scope": False,
    }))
    nlu = LLMNLUClassifier(mock_client)

    state = create_session(MINIMAL_SCRIPT)
    result = await async_process_turn(state, MINIMAL_SCRIPT, "tôi muốn đặt lịch", nlu=nlu)
    assert result.intent == "book"
    assert result.next_step_id == "farewell"


async def test_async_process_turn_nlu_timeout_falls_back():
    """On NLU timeout, falls back to substring matcher."""
    from llm.nlu import LLMNLUClassifier  # noqa: PLC0415

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(side_effect=asyncio.TimeoutError())
    nlu = LLMNLUClassifier(mock_client)

    state = create_session(MINIMAL_SCRIPT)
    # "đặt lịch" matches the "book" intent in the example-based matcher
    result = await async_process_turn(state, MINIMAL_SCRIPT, "đặt lịch", nlu=nlu)
    assert result.next_step_id == "farewell"  # fallback matched


async def test_async_process_turn_no_utterance():
    state = create_session(MINIMAL_SCRIPT)
    result = await async_process_turn(state, MINIMAL_SCRIPT, None)
    assert result.intent is None


# ---------------------------------------------------------------------------
# TTS streamer (mock mode)
# ---------------------------------------------------------------------------


async def test_stream_step_beats_yields_beat():
    from tts.streamer import stream_step_beats  # noqa: PLC0415

    step = {
        "id": "greeting",
        "type": "speak_listen",
        "variants": [{"id": "v1", "beats": [{"text": "Xin chào", "pause_after": "turn"}]}],
    }
    beats = []
    async for beat in stream_step_beats(step, {}, 0, 1):
        beats.append(beat)

    assert len(beats) == 1
    assert beats[0].text == "Xin chào"
    assert beats[0].pause_ms == 1000  # "turn" = 1000ms


async def test_stream_step_beats_reprompt():
    from tts.streamer import stream_step_beats  # noqa: PLC0415

    step = {
        "id": "greeting",
        "variants": [{"id": "v1", "beats": [{"text": "Câu gốc", "pause_after": "none"}]}],
        "reprompt_variants": [
            {"id": "r1", "beats": [{"text": "Reprompt 1", "pause_after": "none"}]},
        ],
    }
    beats = []
    async for beat in stream_step_beats(step, {}, 1, 2):  # no_match_count=1
        beats.append(beat)

    assert beats[0].text == "Reprompt 1"


async def test_stream_step_beats_slot_template():
    from tts.streamer import stream_step_beats  # noqa: PLC0415

    step = {
        "id": "confirm",
        "variants": [{"id": "v1", "beats": [{"text": "Lịch {{date}}", "pause_after": "none"}]}],
    }
    beats = []
    async for beat in stream_step_beats(step, {"date": "ngày 15"}, 0, 1):
        beats.append(beat)

    assert "ngày 15" in beats[0].text


async def test_stream_step_beats_ttfa_first_only():
    from tts.streamer import stream_step_beats  # noqa: PLC0415

    step = {
        "id": "s1",
        "variants": [{"id": "v1", "beats": [
            {"text": "Beat 1", "pause_after": "none"},
            {"text": "Beat 2", "pause_after": "none"},
        ]}],
    }
    beats = []
    async for beat in stream_step_beats(step, {}, 0, 1):
        beats.append(beat)

    assert beats[0].ttfa_ms is not None
    assert beats[1].ttfa_ms is None


# ---------------------------------------------------------------------------
# AudioPipeline integration (mock STT)
# ---------------------------------------------------------------------------


async def test_audio_pipeline_feeds_and_stops():
    from audio.pipeline import AudioPipeline  # noqa: PLC0415
    from stt.faster_whisper_stt import STTResult  # noqa: PLC0415

    mock_stt = MagicMock()
    mock_stt.transcribe_pcm = MagicMock(
        return_value=STTResult(text="xin chào", confidence=0.9, is_final=True)
    )

    pipeline = AudioPipeline(mock_stt, is_ulaw=False)

    import numpy as np  # noqa: PLC0415

    speech_frame = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    for _ in range(5):
        pipeline.feed(speech_frame)

    pipeline.stop()

    results = []
    async for r in pipeline.process():
        results.append(r)

    assert len(results) >= 1
    assert results[0].text == "xin chào"


async def test_audio_pipeline_is_speech_active():
    """is_speech_active reflects VAD state — used for barge-in detection."""
    from audio.pipeline import AudioPipeline  # noqa: PLC0415
    from stt.faster_whisper_stt import STTResult  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    mock_stt = MagicMock()
    mock_stt.transcribe_pcm = MagicMock(
        return_value=STTResult(text="test", confidence=0.9, is_final=True)
    )

    pipeline = AudioPipeline(mock_stt, is_ulaw=False)
    assert not pipeline.is_speech_active  # silent initially

    # Feed a speech frame (above energy threshold)
    speech_frame = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    pipeline.feed(speech_frame)
    # Run one iteration of the pipeline so VAD can process the frame
    await asyncio.sleep(0.025)
    async for _ in _drain_one(pipeline):  # noqa: PLC0415
        break

    pipeline.stop()
    async for _ in pipeline.process():
        pass


async def _drain_one(pipeline):  # type: ignore[no-untyped-def]
    """Helper: process one item from pipeline (for tests)."""
    try:
        async with asyncio.timeout(0.1):
            async for item in pipeline.process():
                yield item
                return
    except TimeoutError:
        pass


async def test_audio_pipeline_async_stt():
    """AudioPipeline supports async STT engines (e.g. ElevenLabsSTT)."""
    from audio.pipeline import AudioPipeline  # noqa: PLC0415
    from stt.faster_whisper_stt import STTResult  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    # Simulate async STT (like ElevenLabsSTT)
    async def async_transcribe(pcm_bytes: bytes, sample_rate: int = 8000) -> STTResult:
        return STTResult(text="async transcript", confidence=0.95, is_final=True)

    mock_stt = MagicMock()
    mock_stt.transcribe_pcm = async_transcribe  # async coroutine function

    pipeline = AudioPipeline(mock_stt, is_ulaw=False)
    assert pipeline._stt_is_async  # should detect async STT

    speech_frame = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    for _ in range(5):
        pipeline.feed(speech_frame)
    pipeline.stop()

    results = []
    async for r in pipeline.process():
        results.append(r)

    assert len(results) >= 1
    assert results[0].text == "async transcript"


async def test_audio_pipeline_barge_in_via_is_speech_active():
    """Pipeline exposes VAD speech state for barge-in (Phase 1.3)."""
    from audio.pipeline import AudioPipeline  # noqa: PLC0415
    from stt.faster_whisper_stt import STTResult  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    mock_stt = MagicMock()
    mock_stt.transcribe_pcm = MagicMock(
        return_value=STTResult(text="barge", confidence=0.9, is_final=True)
    )
    pipeline = AudioPipeline(mock_stt, is_ulaw=False)

    # Before any frames, speech not active
    assert not pipeline.is_speech_active

    # Synthesize a speech-energy frame and feed it directly (bypass queue — test VAD directly)
    speech_pcm = (np.ones(160, dtype=np.int16) * 8000).tobytes()
    pipeline._vad.is_speech(speech_pcm)  # manually trigger VAD

    assert pipeline.is_speech_active
