"""TTSChain.stream_synthesize fallback — regression test for the "engine
construction succeeds, first byte fails" class of bug (real xKiro 503s in
production silenced a whole turn instead of falling back to edge-tts,
because the try/except wrapped generator *construction*, not iteration —
see tts/chain.py::stream_synthesize's docstring)."""

from __future__ import annotations

import pytest

from tts.chain import CircuitBreaker, ElevenLabsQuotaTracker, TTSChain


class _FakeQuota(ElevenLabsQuotaTracker):
    def __init__(self) -> None:
        pass  # skip real Redis wiring


class _FailsOnFirstChunk:
    """Mimics XkiroTTS: construction never raises (it's just building an
    async generator), the failure only surfaces once iterated."""

    name = "flaky"

    async def stream_synthesize(self, text, params=None):  # noqa: ANN001
        async def _gen():
            raise RuntimeError("503 Service Unavailable")
            yield b""  # pragma: no cover — unreachable, keeps this an async gen

        return _gen()


class _WorksFine:
    name = "backup"

    async def stream_synthesize(self, text, params=None):  # noqa: ANN001
        async def _gen():
            yield b"chunk-a"
            yield b"chunk-b"

        return _gen()


def _make_chain(engines: list[object], names: list[str]) -> TTSChain:
    return TTSChain(engines, names, CircuitBreaker(), _FakeQuota())


@pytest.mark.asyncio
async def test_stream_synthesize_falls_back_when_first_chunk_fails():
    chain = _make_chain([_FailsOnFirstChunk(), _WorksFine()], ["flaky", "backup"])

    gen = await chain.stream_synthesize("Dạ, Doctor Check xin nghe ạ.")
    chunks = [c async for c in gen]

    assert chunks == [b"chunk-a", b"chunk-b"]


@pytest.mark.asyncio
async def test_stream_synthesize_opens_circuit_after_threshold_failures():
    chain = _make_chain([_FailsOnFirstChunk(), _WorksFine()], ["flaky", "backup"])

    # CircuitBreaker's default threshold is 3 — one 503 shouldn't trip it,
    # but repeated ones should, same as synthesize()'s existing behaviour.
    for _ in range(3):
        await chain.stream_synthesize("câu bất kỳ")

    assert chain.engine_status()["flaky"] == "open"


@pytest.mark.asyncio
async def test_stream_synthesize_preserves_all_chunks_from_working_engine():
    chain = _make_chain([_WorksFine()], ["backup"])

    gen = await chain.stream_synthesize("câu bất kỳ")
    chunks = [c async for c in gen]

    assert chunks == [b"chunk-a", b"chunk-b"]


@pytest.mark.asyncio
async def test_stream_synthesize_all_engines_failing_returns_empty_not_raise():
    chain = _make_chain([_FailsOnFirstChunk()], ["flaky"])

    gen = await chain.stream_synthesize("câu bất kỳ")
    chunks = [c async for c in gen]

    assert chunks == []
