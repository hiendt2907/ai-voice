#!/usr/bin/env python
"""Vietnamese TTS bake-off harness — Phase 0, task G.4 (D3 decision).

Measures objectively, per engine × per sentence:
  * TTFA  — wall-clock ms from request start to the FIRST audio byte actually
            received from `stream_synthesize()`. This also *detects pseudo-
            streaming*: if TTFA ≈ total synthesis time and the generator
            yields a single chunk, the engine is not really streaming.
  * RTF   — synthesis wall-clock / produced audio duration.
  * dur_s — audio duration, to flag engines reading absurdly fast/slow.
  * chunks / first_chunk_bytes — evidence for the streaming verdict.

It deliberately does NOT score quality. MOS and mispronunciation counts
require native listeners; every generated sample is written to
`bench/tts_samples/<engine>/<engine>_<id>.wav` with an INDEX.md cross-reference
so a human can A/B the same sentence across engines.

Usage (from services/voice/):
    uv run python bench/tts_benchmark.py
    uv run python bench/tts_benchmark.py --engines piper,edge
    uv run python bench/tts_benchmark.py --repeats 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
VOICE_ROOT = BENCH_DIR.parent
SAMPLES_DIR = BENCH_DIR / "tts_samples"

# Make `tts.*` importable when run as `python bench/tts_benchmark.py`.
sys.path.insert(0, str(VOICE_ROOT))

from bench.test_sentences import SENTENCES  # noqa: E402

SAMPLE_RATE = 8000  # every in-repo engine emits int16 PCM @ 8 kHz (telephony)
BYTES_PER_SAMPLE = 2


# --------------------------------------------------------------------------- #
# Result model
# --------------------------------------------------------------------------- #
@dataclass
class Measurement:
    """One synthesis of one sentence by one engine."""

    engine: str
    sentence_id: str
    category: str
    ok: bool
    ttfa_ms: float | None = None
    total_ms: float | None = None
    audio_dur_s: float | None = None
    rtf: float | None = None
    n_chunks: int = 0
    first_chunk_bytes: int = 0
    total_bytes: int = 0
    wav_path: str | None = None
    error: str | None = None


@dataclass
class EngineReport:
    engine: str
    label: str
    available: bool
    skip_reason: str | None = None
    measurements: list[Measurement] = field(default_factory=list)

    def ok_rows(self) -> list[Measurement]:
        return [m for m in self.measurements if m.ok]

    def stat(self, attr: str, fn=statistics.median) -> float | None:
        vals = [getattr(m, attr) for m in self.ok_rows() if getattr(m, attr) is not None]
        return round(fn(vals), 1) if vals else None

    def p90(self, attr: str) -> float | None:
        vals = sorted(
            getattr(m, attr) for m in self.ok_rows() if getattr(m, attr) is not None
        )
        if not vals:
            return None
        idx = min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))
        return round(vals[idx], 1)

    def streaming_verdict(self) -> str:
        rows = self.ok_rows()
        if not rows:
            return "—"
        max_chunks = max(m.n_chunks for m in rows)
        if max_chunks <= 1:
            return "NO (single chunk)"
        # Real streaming => first audio arrives well before synthesis completes.
        ratios = [
            m.ttfa_ms / m.total_ms
            for m in rows
            if m.ttfa_ms is not None and m.total_ms
        ]
        med = statistics.median(ratios) if ratios else 1.0
        if med < 0.6:
            return f"YES (TTFA={med:.0%} of total)"
        return f"pseudo (post-hoc chunking, TTFA={med:.0%} of total)"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def write_wav(path: Path, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(BYTES_PER_SAMPLE)
        f.setframerate(sample_rate)
        f.writeframes(pcm)


async def measure_stream(
    engine_name: str,
    sid: str,
    category: str,
    text: str,
    stream_factory,
    out_path: Path,
    sample_rate: int = SAMPLE_RATE,
) -> Measurement:
    """Drive one `stream_synthesize()` call and time the first real byte.

    `stream_factory(text)` must be an awaitable returning an async generator of
    PCM byte chunks (the interface every engine in `tts/` exposes).
    """
    chunks: list[bytes] = []
    t0 = time.perf_counter()
    ttfa: float | None = None
    try:
        gen = await stream_factory(text)
        async for chunk in gen:
            if not chunk:
                continue
            if ttfa is None:
                ttfa = (time.perf_counter() - t0) * 1000
            chunks.append(chunk)
        total_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:  # engine-level failure — recorded, never fatal
        return Measurement(
            engine=engine_name,
            sentence_id=sid,
            category=category,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )

    pcm = b"".join(chunks)
    if not pcm:
        return Measurement(
            engine=engine_name,
            sentence_id=sid,
            category=category,
            ok=False,
            total_ms=round(total_ms, 1),
            error="empty audio",
        )

    dur = len(pcm) / (sample_rate * BYTES_PER_SAMPLE)
    write_wav(out_path, pcm, sample_rate)
    return Measurement(
        engine=engine_name,
        sentence_id=sid,
        category=category,
        ok=True,
        ttfa_ms=round(ttfa or total_ms, 1),
        total_ms=round(total_ms, 1),
        audio_dur_s=round(dur, 3),
        rtf=round((total_ms / 1000) / dur, 4) if dur else None,
        n_chunks=len(chunks),
        first_chunk_bytes=len(chunks[0]),
        total_bytes=len(pcm),
        wav_path=str(out_path.relative_to(BENCH_DIR)),
    )


def load_dotenv() -> None:
    env_path = VOICE_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# --------------------------------------------------------------------------- #
# Engine runners — each returns an EngineReport
# --------------------------------------------------------------------------- #
async def run_piper(sentences, repeats: int) -> EngineReport:
    rep = EngineReport("piper", "Piper vi_VN-vais1000-medium (local ONNX)", True)
    model = VOICE_ROOT / "models" / "piper" / "vi_VN-vais1000-medium.onnx"
    if not model.exists():
        rep.available = False
        rep.skip_reason = f"model not found at {model}"
        return rep
    try:
        from tts.piper_tts import PiperTTS
    except Exception as exc:
        rep.available = False
        rep.skip_reason = f"import failed: {exc}"
        return rep

    tts = PiperTTS(str(model))
    try:
        await tts.warmup()  # exclude the ~300 ms ONNX JIT from the numbers
    except Exception as exc:
        rep.available = False
        rep.skip_reason = f"warmup failed: {exc}"
        return rep

    for sid, cat, text in sentences:
        for r in range(repeats):
            out = SAMPLES_DIR / "piper" / f"piper_{sid}.wav"
            m = await measure_stream(
                "piper", sid, cat, text,
                lambda t: tts.stream_synthesize(t), out,
            )
            rep.measurements.append(m)
    return rep


async def run_edge(sentences, repeats: int, voice: str) -> EngineReport:
    rep = EngineReport("edge-tts", f"edge-tts {voice} (Microsoft, unofficial)", True)
    try:
        from tts.edge_tts import EdgeTTS
    except Exception as exc:
        rep.available = False
        rep.skip_reason = f"import failed: {exc}"
        return rep

    tts = EdgeTTS(voice=voice)
    slug = voice.replace("vi-VN-", "").replace("Neural", "").lower()
    for sid, cat, text in sentences:
        for r in range(repeats):
            out = SAMPLES_DIR / "edge-tts" / f"edge_{slug}_{sid}.wav"
            m = await measure_stream(
                "edge-tts", sid, cat, text,
                lambda t: tts.stream_synthesize(t), out,
            )
            rep.measurements.append(m)
    return rep


async def run_elevenlabs(sentences, repeats: int, model_id: str) -> EngineReport:
    rep = EngineReport(
        f"elevenlabs:{model_id}", f"ElevenLabs {model_id}", True
    )
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    if not api_key or not voice_id:
        rep.available = False
        rep.skip_reason = "ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID not set in .env"
        return rep
    try:
        from tts.elevenlabs_tts import ElevenLabsTTS
    except Exception as exc:
        rep.available = False
        rep.skip_reason = f"import failed: {exc}"
        return rep

    tts = ElevenLabsTTS(
        api_key=api_key, voice_id=voice_id, model_id=model_id, language_code="vi"
    )
    # One warm call so TLS/connection setup is not billed to sentence 1.
    try:
        gen = await tts.stream_synthesize("Xin chào.")
        async for _ in gen:
            pass
    except Exception as exc:
        rep.available = False
        rep.skip_reason = f"warmup call failed ({model_id}): {exc}"
        return rep

    slug = model_id.replace("eleven_", "")
    for sid, cat, text in sentences:
        for r in range(repeats):
            out = SAMPLES_DIR / f"elevenlabs-{slug}" / f"el_{slug}_{sid}.wav"
            m = await measure_stream(
                rep.engine, sid, cat, text,
                lambda t: tts.stream_synthesize(t), out,
            )
            rep.measurements.append(m)
            if not m.ok and "empty audio" not in (m.error or ""):
                # A hard API failure (bad model id, quota) repeats for every
                # sentence — stop early instead of burning the quota.
                rep.skip_reason = m.error
                return rep
    return rep


def probe_community_models() -> list[EngineReport]:
    """viXTTS / F5-TTS-vi feasibility probe (no fabricated numbers).

    Both are *voice-cloning* models with heavy, conflicting dependency trees;
    this function only reports whether they can be imported from the current
    environment. Actual weights + inference were evaluated out-of-band — see
    the report section in docs/ for the recorded verdict.
    """
    reports: list[EngineReport] = []
    for engine, label, module, note in (
        (
            "vixtts",
            "viXTTS (capleaf/viXTTS, XTTS-v2 Vietnamese finetune)",
            "TTS.api",
            "requires coqui-tts (unmaintained fork); licence Coqui CPML — "
            "non-commercial",
        ),
        (
            "f5-tts-vi",
            "F5-TTS-Vietnamese-ViVoice (hynt/…, 1000 h finetune)",
            "f5_tts.api",
            "requires f5-tts + torch; licence CC-BY-NC-SA-4.0 — non-commercial",
        ),
    ):
        rep = EngineReport(engine, label, False)
        try:
            __import__(module)
            rep.available = True
            rep.skip_reason = (
                f"{module} importable, but no runner wired here — {note}"
            )
        except Exception as exc:
            rep.skip_reason = f"NOT INSTALLED in this env ({type(exc).__name__}). {note}"
        reports.append(rep)
    return reports


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def write_index(reports: list[EngineReport], sentences) -> None:
    by_sentence: dict[str, list[Measurement]] = {sid: [] for sid, _, _ in sentences}
    for rep in reports:
        for m in rep.ok_rows():
            if m.sentence_id in by_sentence and not any(
                x.engine == m.engine for x in by_sentence[m.sentence_id]
            ):
                by_sentence[m.sentence_id].append(m)

    lines = [
        "# TTS bake-off samples — cross-reference index",
        "",
        "Generated by `bench/tts_benchmark.py`. Every WAV is 16-bit mono PCM "
        "@ 8 kHz (telephony band), i.e. exactly what a caller would hear.",
        "",
        "**No quality score is recorded here.** MOS and mispronunciation counts "
        "need native Vietnamese listeners — play the files for the same "
        "sentence id across engines and score them yourself.",
        "",
    ]
    for sid, cat, text in sentences:
        lines.append(f"## `{sid}` — {cat}")
        lines.append("")
        lines.append(f"> {text}")
        lines.append("")
        rows = by_sentence.get(sid, [])
        if not rows:
            lines.append("_no engine produced audio for this sentence_")
            lines.append("")
            continue
        lines.append("| engine | file | dur (s) | TTFA (ms) | RTF |")
        lines.append("|---|---|---|---|---|")
        for m in rows:
            lines.append(
                f"| {m.engine} | `{m.wav_path}` | {m.audio_dur_s} | "
                f"{m.ttfa_ms} | {m.rtf} |"
            )
        lines.append("")

    (SAMPLES_DIR / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def render_markdown(reports: list[EngineReport], repeats: int) -> str:
    out = [
        "| Engine | Runs OK | TTFA med (ms) | TTFA p90 (ms) | RTF med | "
        "Audio dur med (s) | Real streaming? |",
        "|---|---|---|---|---|---|---|",
    ]
    for rep in reports:
        if not rep.ok_rows():
            reason = rep.skip_reason or "no successful run"
            out.append(f"| {rep.label} | 0 | — | — | — | — | not measured: {reason} |")
            continue
        n_ok = len(rep.ok_rows())
        n = len(rep.measurements)
        out.append(
            f"| {rep.label} | {n_ok}/{n} | {rep.stat('ttfa_ms')} | "
            f"{rep.p90('ttfa_ms')} | {rep.stat('rtf')} | "
            f"{rep.stat('audio_dur_s')} | {rep.streaming_verdict()} |"
        )
    return "\n".join(out)


def render_numeric_check(reports: list[EngineReport]) -> str:
    """Per-engine sanity check on the numeral/date/phone stress sentences."""
    out = [
        "| Engine | numeric/date sentences OK | failures |",
        "|---|---|---|",
    ]
    for rep in reports:
        rows = [m for m in rep.measurements if m.category in ("numbers", "tones", "loanword")]
        if not rows:
            continue
        ok = [m for m in rows if m.ok]
        bad = [f"`{m.sentence_id}`: {m.error}" for m in rows if not m.ok]
        out.append(
            f"| {rep.label} | {len(ok)}/{len(rows)} | "
            f"{'; '.join(bad) if bad else 'none'} |"
        )
    return "\n".join(out)


# --------------------------------------------------------------------------- #
async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--engines",
        default="piper,edge,el-v3,el-flash",
        help="comma list: piper,edge,edge-nam,el-v3,el-flash,el-turbo",
    )
    ap.add_argument("--repeats", type=int, default=1, help="runs per sentence")
    ap.add_argument("--limit", type=int, default=0, help="only first N sentences")
    args = ap.parse_args()

    load_dotenv()
    sentences = SENTENCES[: args.limit] if args.limit else SENTENCES
    wanted = {e.strip() for e in args.engines.split(",") if e.strip()}

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    reports: list[EngineReport] = []

    if "piper" in wanted:
        print("[bench] piper …", flush=True)
        reports.append(await run_piper(sentences, args.repeats))
    if "edge" in wanted:
        print("[bench] edge-tts vi-VN-HoaiMyNeural …", flush=True)
        reports.append(await run_edge(sentences, args.repeats, "vi-VN-HoaiMyNeural"))
    if "edge-nam" in wanted:
        print("[bench] edge-tts vi-VN-NamMinhNeural …", flush=True)
        reports.append(await run_edge(sentences, args.repeats, "vi-VN-NamMinhNeural"))
    if "el-v3" in wanted:
        print("[bench] elevenlabs eleven_v3 …", flush=True)
        reports.append(await run_elevenlabs(sentences, args.repeats, "eleven_v3"))
    if "el-flash" in wanted:
        print("[bench] elevenlabs eleven_flash_v2_5 …", flush=True)
        reports.append(
            await run_elevenlabs(sentences, args.repeats, "eleven_flash_v2_5")
        )
    if "el-turbo" in wanted:
        print("[bench] elevenlabs eleven_turbo_v2_5 …", flush=True)
        reports.append(
            await run_elevenlabs(sentences, args.repeats, "eleven_turbo_v2_5")
        )

    reports.extend(probe_community_models())

    write_index(reports, sentences)
    (BENCH_DIR / "tts_benchmark_results.json").write_text(
        json.dumps(
            {
                "sentences": [
                    {"id": s, "category": c, "text": t} for s, c, t in sentences
                ],
                "repeats": args.repeats,
                "reports": [
                    {
                        "engine": r.engine,
                        "label": r.label,
                        "available": r.available,
                        "skip_reason": r.skip_reason,
                        "measurements": [asdict(m) for m in r.measurements],
                    }
                    for r in reports
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(render_markdown(reports, args.repeats))
    print()
    print(render_numeric_check(reports))
    print()
    print(f"[bench] samples → {SAMPLES_DIR}")
    print(f"[bench] index   → {SAMPLES_DIR / 'INDEX.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
