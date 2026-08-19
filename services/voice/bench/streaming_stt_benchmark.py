"""Measures real first-partial-transcript latency for the Phase 2 streaming
STT gateway (/ws/stt) against a real running inference_server.py.

Run against a TEST port (never 8100 — that's production), e.g.:

    STT_MODEL_SIZE=models/phowhisper-medium-ct2 STT_COMPUTE_TYPE=int8 \
    INFERENCE_SERVER_TOKEN=... \
    uv run uvicorn inference_server:app --port 8101 &

    uv run python bench/streaming_stt_benchmark.py \
        --url http://127.0.0.1:8101 --token $INFERENCE_SERVER_TOKEN

For each sample WAV in bench/tts_samples/piper/, streams it as 20ms PCM16
frames (mirroring real call pacing) over a persistent StreamingRemoteSTT
connection and records:
  - t_first_partial: time from the first audio byte sent to the first
    stt.partial received
  - t_final: time from the first audio byte sent to stt.final
  - number of partials emitted before the final

This is real, measured latency — not a projection. See the printed report
for actual numbers; there is no target enforcement here (Phase 2 task 1
explicitly does not require hitting the <=300ms number yet).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import statistics
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stt.streaming_remote_stt import StreamingRemoteSTT, StreamingRemoteSTTError  # noqa: E402

FRAME_MS = 20
SAMPLE_RATE = 8000
BYTES_PER_SAMPLE = 2
FRAME_BYTES = int(SAMPLE_RATE * FRAME_MS / 1000) * BYTES_PER_SAMPLE


def _read_pcm16(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        assert wf.getframerate() == SAMPLE_RATE, f"{path} is not 8kHz ({wf.getframerate()})"
        assert wf.getsampwidth() == 2, f"{path} is not 16-bit PCM"
        return wf.readframes(wf.getnframes())


async def _run_one(url: str, token: str, path: Path, turn_id: str) -> dict:
    pcm = _read_pcm16(path)
    client = StreamingRemoteSTT(url, token=token, sample_rate=SAMPLE_RATE)

    first_partial_at: float | None = None
    final_at: float | None = None
    final_text = ""
    partial_count = 0
    got_final = asyncio.Event()

    async def on_partial(_turn_id: str, _text: str) -> None:
        nonlocal first_partial_at, partial_count
        partial_count += 1
        if first_partial_at is None:
            first_partial_at = time.perf_counter()

    async def on_final(_turn_id: str, text: str, _confidence: float) -> None:
        nonlocal final_at, final_text
        final_at = time.perf_counter()
        final_text = text
        got_final.set()

    await client.connect()
    # The server keeps this connection open for the whole call (persistent
    # WS, per D5) — listen() only returns once *we* close it, so we wait for
    # this turn's stt.final specifically rather than for listen() to return.
    listen_task = asyncio.create_task(
        client.listen(on_partial=on_partial, on_final=on_final)
    )

    t_start = time.perf_counter()
    await client.start_turn(turn_id)
    for offset in range(0, len(pcm), FRAME_BYTES):
        await client.send_audio(pcm[offset : offset + FRAME_BYTES])
        await asyncio.sleep(FRAME_MS / 1000)  # mirror real-time call pacing
    await client.end_turn()

    try:
        await asyncio.wait_for(got_final.wait(), timeout=30.0)
    except TimeoutError:
        print(f"  ! {path.name}: no stt.final within 30s")
    finally:
        await client.close()
        listen_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, StreamingRemoteSTTError):
            await listen_task

    return {
        "sample": path.name,
        "audio_duration_s": len(pcm) / (SAMPLE_RATE * BYTES_PER_SAMPLE),
        "t_first_partial_ms": (
            (first_partial_at - t_start) * 1000 if first_partial_at is not None else None
        ),
        "t_final_ms": (final_at - t_start) * 1000 if final_at is not None else None,
        "partial_count": partial_count,
        "final_text": final_text,
    }


async def _main(url: str, token: str, samples_dir: Path, limit: int) -> None:
    samples = sorted(samples_dir.glob("*.wav"))[:limit]
    if not samples:
        print(f"No .wav samples found under {samples_dir}")
        return

    results = []
    for i, path in enumerate(samples):
        print(f"[{i + 1}/{len(samples)}] {path.name} ...")
        result = await _run_one(url, token, path, turn_id=f"bench-{i}")
        results.append(result)
        print(
            f"    first_partial={result['t_first_partial_ms']!s:>8} ms  "
            f"final={result['t_final_ms']!s:>8} ms  "
            f"partials={result['partial_count']}  text={result['final_text']!r}"
        )

    partials = [r["t_first_partial_ms"] for r in results if r["t_first_partial_ms"] is not None]
    finals = [r["t_final_ms"] for r in results if r["t_final_ms"] is not None]

    print("\n=== Streaming STT bench report (real, measured) ===")
    print(f"samples: {len(results)}  (with a first partial: {len(partials)}, with a final: {len(finals)})")
    if partials:
        print(
            f"first_partial ms: mean={statistics.mean(partials):.0f} "
            f"median={statistics.median(partials):.0f} "
            f"min={min(partials):.0f} max={max(partials):.0f}"
        )
    if finals:
        print(
            f"final ms:         mean={statistics.mean(finals):.0f} "
            f"median={statistics.median(finals):.0f} "
            f"min={min(finals):.0f} max={max(finals):.0f}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8101")
    parser.add_argument("--token", required=True)
    parser.add_argument(
        "--samples-dir",
        default=str(Path(__file__).resolve().parent / "tts_samples" / "piper"),
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    asyncio.run(_main(args.url, args.token, Path(args.samples_dir), args.limit))
