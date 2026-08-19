#!/usr/bin/env python
"""Vietnamese STT benchmark harness — Phase 0, task G.3 (D2 decision).

Compares candidate STT engines for the DoctorCheck phone agent on a fixed
Vietnamese telephony test set (`bench/testset_vi.py`, 20 utterances covering
intents, digits, dates/times, proper names, domain vocabulary, short
confirmations, and long multi-slot sentences).

Ground-truth audio is synthesized locally with Piper (`vi_VN-vais1000-medium`,
already 8kHz PCM) and round-tripped through the same G.711 μ-law codec the
runtime uses (`audio/codec.py`) so the STT engines see telephony-band audio,
not studio-clean audio. This is a *known limitation*, not hidden: TTS-derived
audio is cleaner than a real caller on a real phone line (no crosstalk, no
line noise, consistent mic gain, no regional-accent variety beyond what one
Piper voice produces). Treat WER numbers here as a floor, not a ceiling —
real-caller WER will be higher for every engine.

Metrics per (engine, utterance):
  * WER      — jiwer, after lowercasing + punctuation-stripping + running
               `tts.text_normalizer.normalize()` on both reference and
               hypothesis so digit-form output ("0908...") and word-form
               output ("không chín không tám...") score identically.
  * latency  — one-shot transcribe wall-clock (every engine wired into this
               repo today is one-shot; none produce partial transcripts).
  * RTF      — latency / audio duration.

Only engines that actually load and run on this machine are scored. Anything
that cannot run here (missing weights, no internet, incompatible dep) is
reported as unavailable with a stated reason — never a fabricated number.

Usage (from services/voice/):
    uv run python bench/stt_benchmark.py
    uv run python bench/stt_benchmark.py --engines faster_whisper_small,elevenlabs
    uv run python bench/stt_benchmark.py --list-engines
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import statistics
import string
import sys
import time
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
VOICE_ROOT = BENCH_DIR.parent
AUDIO_DIR = BENCH_DIR / "stt_audio"
RESULTS_DIR = BENCH_DIR / "results"

sys.path.insert(0, str(VOICE_ROOT))

from audio.codec import pcm_to_ulaw, ulaw_to_pcm  # noqa: E402
from bench.testset_vi import TEST_SET, Utterance  # noqa: E402
from tts.text_normalizer import normalize as vi_normalize  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("stt_benchmark")

SAMPLE_RATE = 8000
BYTES_PER_SAMPLE = 2


# --------------------------------------------------------------------------- #
# Result model
# --------------------------------------------------------------------------- #
@dataclass
class Measurement:
    engine: str
    uid: str
    tags: tuple[str, ...]
    ok: bool
    hypothesis: str | None = None
    reference: str | None = None
    wer: float | None = None
    latency_ms: float | None = None
    audio_dur_s: float | None = None
    rtf: float | None = None
    error: str | None = None


@dataclass
class EngineReport:
    engine: str
    label: str
    apple_silicon_accelerated: bool
    available: bool
    skip_reason: str | None = None
    measurements: list[Measurement] = field(default_factory=list)

    def ok_rows(self) -> list[Measurement]:
        return [m for m in self.measurements if m.ok]

    def stat(self, attr: str, fn: Any = statistics.median) -> float | None:
        vals = [getattr(m, attr) for m in self.ok_rows() if getattr(m, attr) is not None]
        return round(fn(vals), 4) if vals else None


# --------------------------------------------------------------------------- #
# Ground-truth audio: synth with Piper, round-trip through μ-law, cache to disk
# --------------------------------------------------------------------------- #
def _wav_path(uid: str) -> Path:
    return AUDIO_DIR / f"{uid}.wav"


async def _synth_ground_truth_audio(force: bool = False) -> None:
    """Synthesize every TEST_SET utterance to 8kHz PCM WAV via Piper, then
    round-trip through G.711 μ-law to simulate the telephony codec path.
    Cached to bench/stt_audio/<uid>.wav — safe to re-run.
    """
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    missing = [u for u in TEST_SET if force or not _wav_path(u.uid).exists()]
    if not missing:
        logger.info("Ground-truth audio already cached (%d files).", len(TEST_SET))
        return

    from tts.piper_tts import PiperTTS  # noqa: PLC0415 — heavy import, load lazily

    piper = PiperTTS()
    logger.info("Synthesizing %d ground-truth utterances with Piper…", len(missing))
    for u in missing:
        pcm = await piper.synthesize(u.text)
        if not pcm:
            logger.warning("Piper produced empty audio for %s", u.uid)
            continue
        # Telephony round trip: PCM16 8k -> μ-law -> PCM16 8k (lossy, matches
        # what a real caller's audio looks like after the G.711 codec path).
        ulaw = pcm_to_ulaw(_pcm_bytes_to_array(pcm))
        telephony_pcm = ulaw_to_pcm(ulaw).tobytes()
        _write_wav(_wav_path(u.uid), telephony_pcm)
    logger.info("Ground-truth audio ready in %s", AUDIO_DIR)


def _pcm_bytes_to_array(pcm_bytes: bytes) -> Any:
    import numpy as np

    return np.frombuffer(pcm_bytes, dtype=np.int16)


def _write_wav(path: Path, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(BYTES_PER_SAMPLE)
        f.setframerate(sample_rate)
        f.writeframes(pcm)


def _load_wav_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as f:
        return f.readframes(f.getnframes())


def _audio_duration_s(pcm_bytes: bytes) -> float:
    return len(pcm_bytes) / BYTES_PER_SAMPLE / SAMPLE_RATE


def _upsample_16k(pcm_bytes: bytes) -> Any:
    """8kHz PCM16 bytes -> 16kHz float32 array via polyphase resampling.

    Engines that accept a raw array (no sample-rate metadata honored) need
    this done explicitly — see PhoWhisperEngine's docstring for the empirical
    reason. Mirrors stt/sensevoice_stt.py's existing resample approach.
    """
    import numpy as np
    from scipy.signal import resample_poly

    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return resample_poly(samples, 2, 1).astype(np.float32)


# --------------------------------------------------------------------------- #
# WER scoring
# --------------------------------------------------------------------------- #
_PUNCT_RE = re.compile(f"[{re.escape(string.punctuation)}]")


def _clean_for_wer(text: str) -> str:
    text = vi_normalize(text)  # spell out any remaining digits as VN words
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _wer(reference: str, hypothesis: str) -> float:
    import jiwer

    ref = _clean_for_wer(reference)
    hyp = _clean_for_wer(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return float(jiwer.wer(ref, hyp))


# --------------------------------------------------------------------------- #
# Engine adapters — each returns (label, apple_silicon, loader, transcribe_fn)
# transcribe_fn(pcm_bytes) -> str, may be sync or async.
# --------------------------------------------------------------------------- #
class EngineUnavailableError(Exception):
    pass


class Engine:
    key: str
    label: str
    apple_silicon: bool

    async def load(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    async def transcribe(self, pcm_bytes: bytes) -> str:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None:
        pass


class FasterWhisperEngine(Engine):
    def __init__(self, model_size: str) -> None:
        self.key = f"faster_whisper_{model_size}"
        self.label = f"faster-whisper ({model_size})"
        self.apple_silicon = False
        self._model_size = model_size
        self._stt: Any = None

    async def load(self) -> None:
        try:
            from stt.faster_whisper_stt import FasterWhisperSTT  # noqa: PLC0415
        except ImportError as exc:
            raise EngineUnavailableError(f"faster-whisper not installed: {exc}") from exc
        try:
            self._stt = await asyncio.to_thread(
                lambda: FasterWhisperSTT(model_size=self._model_size, device="cpu", compute_type="int8")
            )
        except Exception as exc:  # noqa: BLE001 — model download/load failure
            raise EngineUnavailableError(f"model load failed: {exc}") from exc

    async def transcribe(self, pcm_bytes: bytes) -> str:
        assert self._stt is not None
        result = await asyncio.to_thread(self._stt.transcribe_pcm, pcm_bytes, SAMPLE_RATE)
        return result.text


class PhoWhisperEngine(Engine):
    """vinai/PhoWhisper-{small,medium} via transformers ASR pipeline.

    Not converted to CTranslate2 (D2's stated ideal) — that conversion step
    was out of scope for this benchmark pass; transformers pipeline gives an
    honest same-hardware comparison of the model's Vietnamese accuracy, at
    the cost of a slower runtime than a CT2 build would give. Latency numbers
    below should be read as "transformers-pipeline latency", not a ceiling on
    what PhoWhisper could achieve once converted.
    """

    def __init__(self, size: str) -> None:
        import torch

        self.key = f"phowhisper_{size}"
        self.label = f"PhoWhisper-{size} (transformers, unconverted)"
        self.apple_silicon = bool(torch.backends.mps.is_available())
        self._model_id = f"vinai/PhoWhisper-{size}"
        self._pipe: Any = None

    def _load_sync(self) -> Any:
        from transformers import pipeline

        return pipeline(
            "automatic-speech-recognition",
            model=self._model_id,
            device="mps" if self.apple_silicon else "cpu",
        )

    async def load(self) -> None:
        try:
            self._pipe = await asyncio.to_thread(self._load_sync)
        except Exception as exc:  # noqa: BLE001
            raise EngineUnavailableError(f"{self._model_id} load failed: {exc}") from exc

    def _transcribe_sync(self, pcm_bytes: bytes) -> str:
        # transformers' ASR pipeline does NOT reliably resample when passed a
        # raw array + sampling_rate != the model's native rate (verified
        # empirically: feeding 8kHz directly makes Whisper hear the audio at
        # ~2x speed and hallucinate). Upsample explicitly to 16kHz first —
        # this also directly answers D2's "does 8k→16k upsampling help"
        # question for every whisper-family engine in this harness.
        samples16k = _upsample_16k(pcm_bytes)
        out = self._pipe({"array": samples16k, "sampling_rate": 16000}, generate_kwargs={"language": "vi"})
        return str(out.get("text", "")).strip()

    async def transcribe(self, pcm_bytes: bytes) -> str:
        return await asyncio.to_thread(self._transcribe_sync, pcm_bytes)


class MlxWhisperEngine(Engine):
    """MLX-Whisper — Apple-Silicon-native port, runs on the M-series GPU/ANE."""

    def __init__(self, hf_repo: str = "mlx-community/whisper-small-mlx") -> None:
        self.key = "mlx_whisper_small"
        self.label = f"MLX-Whisper ({hf_repo.split('/')[-1]})"
        self.apple_silicon = True
        self._hf_repo = hf_repo
        self._mlx_whisper: Any = None

    async def load(self) -> None:
        try:
            import mlx_whisper  # noqa: PLC0415
        except ImportError as exc:
            raise EngineUnavailableError(f"mlx-whisper not installed: {exc}") from exc
        self._mlx_whisper = mlx_whisper
        # Trigger a tiny warmup transcription to force the weight download/load
        # to happen here (load phase), not inside the first timed measurement.
        try:
            import numpy as np

            silence = np.zeros(16000, dtype=np.float32)
            await asyncio.to_thread(
                mlx_whisper.transcribe, silence, path_or_hf_repo=self._hf_repo, language="vi"
            )
        except Exception as exc:  # noqa: BLE001
            raise EngineUnavailableError(f"{self._hf_repo} load/warmup failed: {exc}") from exc

    def _transcribe_sync(self, pcm_bytes: bytes) -> str:
        samples16k = _upsample_16k(pcm_bytes)
        out = self._mlx_whisper.transcribe(samples16k, path_or_hf_repo=self._hf_repo, language="vi")
        return str(out.get("text", "")).strip()

    async def transcribe(self, pcm_bytes: bytes) -> str:
        return await asyncio.to_thread(self._transcribe_sync, pcm_bytes)


class ElevenLabsEngine(Engine):
    def __init__(self) -> None:
        self.key = "elevenlabs_scribe"
        self.label = "ElevenLabs Scribe v2 (cloud)"
        self.apple_silicon = False
        self._stt: Any = None

    async def load(self) -> None:
        import os

        from dotenv import load_dotenv

        load_dotenv(VOICE_ROOT / ".env")
        api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            raise EngineUnavailableError("ELEVENLABS_API_KEY not set in services/voice/.env")
        from stt.elevenlabs_stt import ElevenLabsSTT  # noqa: PLC0415

        self._stt = ElevenLabsSTT(api_key=api_key, language_code="vi")
        # Cheap connectivity check with a real (non-silent) clip — Scribe
        # rejects all-silence audio with 400, which is not a key/auth problem —
        # so a bad key or endpoint failure fails at load time, not scattered
        # across 20 timed measurements.
        probe_path = _wav_path(TEST_SET[0].uid)
        if not probe_path.exists():
            raise EngineUnavailableError("ground-truth audio not synthesized yet")
        try:
            probe_pcm = _load_wav_pcm(probe_path)
            await self._stt.transcribe_pcm(probe_pcm, SAMPLE_RATE)
        except Exception as exc:  # noqa: BLE001
            raise EngineUnavailableError(f"ElevenLabs Scribe request failed: {exc}") from exc

    async def transcribe(self, pcm_bytes: bytes) -> str:
        assert self._stt is not None
        result = await self._stt.transcribe_pcm(pcm_bytes, SAMPLE_RATE)
        return result.text

    async def aclose(self) -> None:
        if self._stt is not None:
            await self._stt.aclose()


class SenseVoiceEngine(Engine):
    """SenseVoiceSmall — officially supports zh/yue/en/ja/ko, NOT Vietnamese.

    Run anyway (language="vi" is accepted by the API but is not a supported
    language per the model card) to produce real WER evidence for the
    "exclude SenseVoice for Vietnamese" recommendation in D2, instead of
    excluding it on the strength of the model card alone.
    """

    def __init__(self) -> None:
        self.key = "sensevoice"
        self.label = "SenseVoiceSmall (lang=vi, UNSUPPORTED per model card)"
        self.apple_silicon = False
        self._stt: Any = None

    async def load(self) -> None:
        try:
            from stt.sensevoice_stt import SenseVoiceSTT  # noqa: PLC0415
        except ImportError as exc:
            raise EngineUnavailableError(f"funasr not installed: {exc}") from exc
        try:
            self._stt = await asyncio.to_thread(lambda: SenseVoiceSTT(device="cpu"))
        except Exception as exc:  # noqa: BLE001
            raise EngineUnavailableError(f"SenseVoiceSmall load failed: {exc}") from exc

    async def transcribe(self, pcm_bytes: bytes) -> str:
        assert self._stt is not None
        result = await asyncio.to_thread(self._stt.transcribe_pcm, pcm_bytes, SAMPLE_RATE)
        return result.text


ENGINE_FACTORIES: dict[str, type[Engine] | object] = {
    "faster_whisper_small": lambda: FasterWhisperEngine("small"),
    "faster_whisper_medium": lambda: FasterWhisperEngine("medium"),
    "phowhisper_small": lambda: PhoWhisperEngine("small"),
    "phowhisper_medium": lambda: PhoWhisperEngine("medium"),
    "mlx_whisper_small": lambda: MlxWhisperEngine(),
    "elevenlabs_scribe": lambda: ElevenLabsEngine(),
    "sensevoice": lambda: SenseVoiceEngine(),
}


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
async def run_engine(name: str, test_set: tuple[Utterance, ...]) -> EngineReport:
    factory = ENGINE_FACTORIES[name]
    engine: Engine = factory()  # type: ignore[operator]
    report = EngineReport(
        engine=engine.key, label=engine.label, apple_silicon_accelerated=engine.apple_silicon, available=False
    )

    t_load0 = time.perf_counter()
    try:
        await engine.load()
    except EngineUnavailableError as exc:
        report.skip_reason = str(exc)
        logger.warning("[%s] unavailable: %s", name, exc)
        return report
    except Exception as exc:  # noqa: BLE001 — never crash the whole run
        report.skip_reason = f"unexpected load error: {exc!r}"
        logger.exception("[%s] unexpected load error", name)
        return report
    load_s = time.perf_counter() - t_load0
    logger.info("[%s] loaded in %.1fs", name, load_s)
    report.available = True
    report.apple_silicon_accelerated = engine.apple_silicon  # may be set during load()

    for u in test_set:
        wav_path = _wav_path(u.uid)
        pcm = _load_wav_pcm(wav_path)
        dur_s = _audio_duration_s(pcm)
        t0 = time.perf_counter()
        try:
            hyp = await engine.transcribe(pcm)
            latency_ms = (time.perf_counter() - t0) * 1000
            wer = _wer(u.text, hyp)
            rtf = (latency_ms / 1000) / dur_s if dur_s > 0 else None
            report.measurements.append(
                Measurement(
                    engine=engine.key,
                    uid=u.uid,
                    tags=u.tags,
                    ok=True,
                    hypothesis=hyp,
                    reference=u.text,
                    wer=wer,
                    latency_ms=round(latency_ms, 1),
                    audio_dur_s=round(dur_s, 2),
                    rtf=round(rtf, 3) if rtf is not None else None,
                )
            )
        except Exception as exc:  # noqa: BLE001
            report.measurements.append(
                Measurement(engine=engine.key, uid=u.uid, tags=u.tags, ok=False, error=repr(exc))
            )
            logger.warning("[%s] %s failed: %r", name, u.uid, exc)

    await engine.aclose()
    return report


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def render_markdown(reports: list[EngineReport]) -> str:
    lines: list[str] = []
    lines.append("| Engine | Apple Silicon | Available | N ok/total | Median WER | Mean WER | Median latency (ms) | Median RTF | Notes |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(reports, key=lambda r: (not r.available, r.stat("wer") if r.available else 99)):
        n_ok = len(r.ok_rows())
        n_total = len(r.measurements) if r.measurements else len(TEST_SET)
        if not r.available:
            lines.append(
                f"| {r.label} | {'yes' if r.apple_silicon_accelerated else 'no'} | NO | — | — | — | — | — | "
                f"not khả thi trong phạm vi task này — {r.skip_reason} |"
            )
            continue
        med_wer = r.stat("wer")
        mean_wer = r.stat("wer", statistics.mean)
        med_lat = r.stat("latency_ms")
        med_rtf = r.stat("rtf")
        lines.append(
            f"| {r.label} | {'yes' if r.apple_silicon_accelerated else 'no'} | yes | {n_ok}/{n_total} | "
            f"{med_wer if med_wer is not None else '—'} | {mean_wer if mean_wer is not None else '—'} | "
            f"{med_lat if med_lat is not None else '—'} | {med_rtf if med_rtf is not None else '—'} | |"
        )
    return "\n".join(lines)


def save_json(reports: list[EngineReport], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            **{k: v for k, v in asdict(r).items() if k != "measurements"},
            "measurements": [asdict(m) for m in r.measurements],
        }
        for r in reports
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engines", type=str, default=None, help="Comma-separated engine keys (default: all)")
    parser.add_argument("--list-engines", action="store_true")
    parser.add_argument("--force-resynth", action="store_true", help="Re-synthesize ground-truth audio")
    parser.add_argument("--out", type=str, default=None, help="JSON output path")
    args = parser.parse_args()

    if args.list_engines:
        for k in ENGINE_FACTORIES:
            print(k)
        return

    engines = list(ENGINE_FACTORIES) if not args.engines else [e.strip() for e in args.engines.split(",")]
    unknown = [e for e in engines if e not in ENGINE_FACTORIES]
    if unknown:
        raise SystemExit(f"Unknown engine(s): {unknown}. Known: {list(ENGINE_FACTORIES)}")

    await _synth_ground_truth_audio(force=args.force_resynth)

    reports: list[EngineReport] = []
    for name in engines:
        print(f"\n=== Running {name} ===", file=sys.stderr)
        report = await run_engine(name, TEST_SET)
        reports.append(report)
        if report.available:
            print(
                f"  {report.label}: {len(report.ok_rows())}/{len(report.measurements)} ok, "
                f"median WER={report.stat('wer')}, median latency={report.stat('latency_ms')}ms, "
                f"median RTF={report.stat('rtf')}",
                file=sys.stderr,
            )
        else:
            print(f"  SKIPPED: {report.skip_reason}", file=sys.stderr)

    print("\n" + render_markdown(reports))

    out_path = Path(args.out) if args.out else RESULTS_DIR / f"stt_benchmark_{int(time.time())}.json"
    save_json(reports, out_path)
    print(f"\nSaved raw results to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
