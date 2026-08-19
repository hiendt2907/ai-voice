"""One-shot script: pre-record all filler phrases with Piper TTS.

Run once to generate the audio cache:
    uv run python -m tts.generate_fillers

Output: tts/filler_audio/<context>/<index>.wav (int16 PCM, 8000Hz, mono)
"""

from __future__ import annotations

import asyncio
import hashlib
import wave
from pathlib import Path

from tts.fillers import _POOLS
from tts.piper_tts import PiperTTS

_OUT_DIR = Path(__file__).parent / "filler_audio"
_SR = 8000


def _write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # int16
        w.setframerate(_SR)
        w.writeframes(pcm)


async def main() -> None:
    tts = PiperTTS()
    await tts.warmup()

    total = 0
    for context, phrases in _POOLS.items():
        for phrase in phrases:
            if "{value}" in phrase:
                continue  # skip template phrases — generated dynamically
            key = hashlib.md5(phrase.encode()).hexdigest()[:8]
            out_path = _OUT_DIR / context / f"{key}.wav"
            if out_path.exists():
                print("  skip (exists): %s  '%s'" % (out_path.name, phrase[:40]))
                continue
            pcm = await tts.synthesize(phrase)
            _write_wav(out_path, pcm)
            total += 1
            print("  wrote: %s  '%s'" % (
                str(out_path.relative_to(Path(__file__).parent.parent)),
                phrase[:40],
            ))

    print("\nDone -- %d new files generated in %s" % (total, _OUT_DIR))


if __name__ == "__main__":
    asyncio.run(main())
