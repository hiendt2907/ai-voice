"""Real-model test for PiperTTS.stream_synthesize's true-streaming fix.

Loads the actual vi_VN-vais1000-medium ONNX model (already vendored under
services/voice/models/piper/ for local dev) — no mocks — and confirms
multi-sentence text now yields more than one chunk progressively, closing
the "RemoteTTS/PiperTTS is a pseudo-stream" gap from
docs/ai-streaming-voice-architecture-proposal.md §197/§1074/§1182.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tts.piper_tts import PiperTTS

_MODEL_PATH = (
    Path(__file__).parent.parent / "models" / "piper" / "vi_VN-vais1000-medium.onnx"
)

pytestmark = pytest.mark.skipif(
    not _MODEL_PATH.exists(),
    reason="Piper model weights not present in this environment (local-inference extra)",
)


async def test_stream_synthesize_yields_multiple_chunks_for_multi_sentence_text():
    tts = PiperTTS()
    text = "Dạ, anh chị giữ máy giúp em. Để em kiểm tra chính xác giờ cho mình ạ."

    gen = await tts.stream_synthesize(text)
    chunks = [c async for c in gen]

    assert len(chunks) >= 2, "multi-sentence text should stream more than one chunk"
    assert all(len(c) > 0 for c in chunks)


async def test_stream_synthesize_first_chunk_arrives_before_full_synthesis_completes():
    """The whole point of the fix: TTFA should track first-SENTENCE synthesis
    time, not whole-utterance synthesis time. Compare stream_synthesize's
    time-to-first-chunk against synthesize()'s total wall time for the same
    multi-sentence text."""
    tts = PiperTTS()
    text = (
        "Dạ, hiện tại buổi sáng ngày thứ Sáu phòng khám vẫn còn trống lịch ạ. "
        "Em đặt luôn cho mình nhé? Anh chị vui lòng giữ máy trong giây lát ạ."
    )

    t0 = time.perf_counter()
    pcm = await tts.synthesize(text)
    full_synth_s = time.perf_counter() - t0
    assert len(pcm) > 0

    t0 = time.perf_counter()
    gen = await tts.stream_synthesize(text)
    first_chunk = await gen.__anext__()
    ttfa_s = time.perf_counter() - t0
    async for _ in gen:
        pass  # drain

    assert len(first_chunk) > 0
    assert ttfa_s < full_synth_s, (
        f"streaming TTFA ({ttfa_s * 1000:.1f}ms) should beat whole-utterance "
        f"synthesis time ({full_synth_s * 1000:.1f}ms) for multi-sentence text"
    )
