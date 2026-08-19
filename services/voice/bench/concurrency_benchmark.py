"""M4 concurrency budget benchmark (Phase 0, task G.5).

Measures the real cost of running STT + LLM + TTS *simultaneously* on this
MacBook, which is the number that drives admission control. Single-engine
benchmarks flatter the machine; this one deliberately does not.

Model of a "call": ``TURNS_PER_CALL`` sequential turns, each turn being

    STT(pcm) -> LLM(streamed, TTFT + tok/s measured) -> TTS(reply text)

``N`` such calls run concurrently via ``asyncio.gather``. A background sampler
records system CPU/memory and per-process CPU for the inference server and the
Ollama runner while each level runs.

Safety: levels run smallest-first and the run aborts before the next level if
the machine shows sustained saturation (see ``ABORT_*`` below) or if the wall
clock budget is exhausted. This box serves production traffic.

Usage (from ``services/voice/``)::

    uv run python bench/concurrency_benchmark.py
    uv run python bench/concurrency_benchmark.py --levels 1,2,4 --turns 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import psutil

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

INFERENCE_URL = "http://localhost:8100"
OLLAMA_URL = "http://localhost:11434"
LLM_MODEL = "qwen3:8b"

TURNS_PER_CALL = 3
DEFAULT_LEVELS = (1, 2, 4, 8)

STT_SAMPLE_RATE = 8000
LLM_MAX_TOKENS = 64
REQUEST_TIMEOUT_S = 120.0

SAMPLE_INTERVAL_S = 0.5
COOLDOWN_S = 8.0
TOTAL_BUDGET_S = 15 * 60  # never run longer than this in one go

# Abort thresholds — stop escalating N when the box is clearly saturated.
ABORT_CPU_PCT = 97.0  # sustained total CPU
ABORT_CPU_SUSTAIN_S = 45.0
ABORT_MEM_PCT = 93.0
ABORT_SWAP_GROWTH_MB = 2048.0
ABORT_ERROR_RATE = 0.10

# Acceptance thresholds for real-time voice, from proposal §I.1.
TARGET_LLM_TTFT_P95_MS = 500.0
TARGET_TTS_TTFA_P95_MS = 350.0
TARGET_STT_P95_MS = 350.0
TARGET_TURN_P95_MS = 1200.0  # speech end -> first agent audio (p95 target)
TARGET_TURN_CEILING_MS = 1500.0

# Vietnamese caller utterances — synthesized once via Piper, then replayed
# into STT so the STT input is real speech-shaped audio, not noise.
CALLER_UTTERANCES = [
    "Xin chào, tôi muốn đặt lịch khám tổng quát vào sáng thứ ba tuần sau.",
    "Cho tôi hỏi phòng khám có làm việc vào cuối tuần không ạ.",
    "Tôi tên là Nguyễn Văn Hùng, số điện thoại không chín tám bảy sáu năm bốn ba hai một.",
]

SYSTEM_PROMPT = (
    "Bạn là nhân viên tổng đài của phòng khám DoctorCheck. "
    "Trả lời ngắn gọn, thân thiện, tối đa hai câu."
)

OUT_DIR = Path(__file__).resolve().parent / "results"


# --------------------------------------------------------------------------
# Stage timings
# --------------------------------------------------------------------------


@dataclass
class TurnSample:
    stt_ms: float
    llm_ttft_ms: float
    llm_total_ms: float
    llm_tokens: int
    tts_ttfa_ms: float
    turn_ms: float

    @property
    def llm_tps(self) -> float:
        gen_s = max(self.llm_total_ms - self.llm_ttft_ms, 1.0) / 1000.0
        return self.llm_tokens / gen_s if self.llm_tokens else 0.0

    @property
    def response_ms(self) -> float:
        """Speech end -> first agent audio: STT + LLM TTFT + TTS TTFA."""
        return self.stt_ms + self.llm_ttft_ms + self.tts_ttfa_ms


@dataclass
class LevelResult:
    n: int
    samples: list[TurnSample] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    wall_s: float = 0.0
    res: dict[str, Any] = field(default_factory=dict)


def pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = min(int(round(q * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[idx]


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"p50": float("nan"), "p95": float("nan"), "mean": float("nan")}
    return {
        "p50": pct(values, 0.50),
        "p95": pct(values, 0.95),
        "mean": statistics.fmean(values),
    }


# --------------------------------------------------------------------------
# Resource sampler
# --------------------------------------------------------------------------


class ResourceSampler(threading.Thread):
    """Samples system + per-process load on a background thread."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._halt = threading.Event()
        self.cpu: list[float] = []
        self.mem_pct: list[float] = []
        self.mem_used_gb: list[float] = []
        self.swap_mb: list[float] = []
        self.swap_growth_mb: list[float] = []
        self.proc_cpu: dict[str, list[float]] = {"inference": [], "ollama": []}
        self.proc_rss_gb: dict[str, list[float]] = {"inference": [], "ollama": []}
        self._procs = _find_procs()
        for group in self._procs.values():
            for p in group:
                try:
                    p.cpu_percent(None)
                except psutil.Error:
                    pass
        psutil.cpu_percent(None)
        # Baseline swap at sampler start. This box already runs other
        # long-lived processes (Ollama models, etc.) that can sit on several
        # GB of pre-existing swap; what matters for the abort decision is how
        # much *more* swap this benchmark run pushes the box into, not the
        # absolute total.
        self._swap_baseline_mb = psutil.swap_memory().used / 1e6

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                self.cpu.append(psutil.cpu_percent(None))
                vm = psutil.virtual_memory()
                self.mem_pct.append(vm.percent)
                self.mem_used_gb.append((vm.total - vm.available) / 1e9)
                swap_now = psutil.swap_memory().used / 1e6
                self.swap_mb.append(swap_now)
                self.swap_growth_mb.append(max(0.0, swap_now - self._swap_baseline_mb))
                for label, group in self._procs.items():
                    cpu = 0.0
                    rss = 0.0
                    for p in group:
                        try:
                            cpu += p.cpu_percent(None)
                            rss += p.memory_info().rss
                        except psutil.Error:
                            continue
                    self.proc_cpu[label].append(cpu)
                    self.proc_rss_gb[label].append(rss / 1e9)
            except psutil.Error:
                pass
            self._halt.wait(SAMPLE_INTERVAL_S)

    def stop(self) -> None:
        self._halt.set()
        self.join(timeout=3.0)

    def sustained_cpu_seconds(self, threshold: float) -> float:
        """Longest contiguous stretch above ``threshold``, in seconds."""
        best = run = 0
        for v in self.cpu:
            run = run + 1 if v >= threshold else 0
            best = max(best, run)
        return best * SAMPLE_INTERVAL_S

    def snapshot(self) -> dict[str, Any]:
        def m(vals: list[float], fn: Any = max) -> float:
            return round(fn(vals), 1) if vals else float("nan")

        return {
            "cpu_mean": m(self.cpu, statistics.fmean),
            "cpu_max": m(self.cpu),
            "cpu_sustained_97_s": self.sustained_cpu_seconds(ABORT_CPU_PCT),
            "mem_pct_max": m(self.mem_pct),
            "mem_used_gb_max": m(self.mem_used_gb),
            "swap_mb_max": m(self.swap_mb),
            "swap_growth_mb_max": m(self.swap_growth_mb),
            "inference_cpu_mean": m(self.proc_cpu["inference"], statistics.fmean),
            "inference_cpu_max": m(self.proc_cpu["inference"]),
            "inference_rss_gb_max": m(self.proc_rss_gb["inference"]),
            "ollama_cpu_mean": m(self.proc_cpu["ollama"], statistics.fmean),
            "ollama_cpu_max": m(self.proc_cpu["ollama"]),
            "ollama_rss_gb_max": m(self.proc_rss_gb["ollama"]),
        }


def _find_procs() -> dict[str, list[psutil.Process]]:
    """Locate the inference server and Ollama runner processes."""
    found: dict[str, list[psutil.Process]] = {"inference": [], "ollama": []}
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (p.info["name"] or "").lower()
            cmd = " ".join(p.info["cmdline"] or "").lower()
        except psutil.Error:
            continue
        if "inference_server" in cmd:
            found["inference"].append(p)
        elif "ollama" in name or "llama-server" in name or "ollama" in cmd:
            found["ollama"].append(p)
    return found


# --------------------------------------------------------------------------
# Engine calls
# --------------------------------------------------------------------------


async def tts_pcm(client: httpx.AsyncClient, text: str) -> tuple[bytes, float]:
    """POST /tts/synthesize -> (pcm16 mono 8k, time-to-first-audio ms).

    The endpoint is one-shot, so TTFA here is the full synthesis latency —
    the honest number for the current non-streaming server.
    """
    t0 = time.perf_counter()
    resp = await client.post(f"{INFERENCE_URL}/tts/synthesize", json={"text": text})
    resp.raise_for_status()
    return resp.content, (time.perf_counter() - t0) * 1000.0


async def stt_text(client: httpx.AsyncClient, pcm: bytes) -> tuple[str, float]:
    t0 = time.perf_counter()
    resp = await client.post(
        f"{INFERENCE_URL}/stt/transcribe",
        params={"sample_rate": STT_SAMPLE_RATE},
        content=pcm,
        headers={"Content-Type": "application/octet-stream"},
    )
    resp.raise_for_status()
    return resp.json()["text"], (time.perf_counter() - t0) * 1000.0


async def llm_stream(
    client: httpx.AsyncClient, messages: list[dict[str, str]]
) -> tuple[str, float, float, int]:
    """Streamed chat completion -> (text, ttft_ms, total_ms, eval_tokens).

    ``think`` is disabled: qwen3 reasoning tokens must never sit on the
    latency path for a live call.
    """
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": {"num_predict": LLM_MAX_TOKENS, "temperature": 0.3},
    }
    t0 = time.perf_counter()
    ttft = float("nan")
    tokens = 0
    parts: list[str] = []
    async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            chunk = json.loads(line)
            content = chunk.get("message", {}).get("content", "")
            if content and ttft != ttft:  # NaN check: first content token
                ttft = (time.perf_counter() - t0) * 1000.0
            if content:
                parts.append(content)
            if chunk.get("done"):
                tokens = int(chunk.get("eval_count") or 0)
    total = (time.perf_counter() - t0) * 1000.0
    if ttft != ttft:
        ttft = total
    return "".join(parts), ttft, total, tokens


# --------------------------------------------------------------------------
# Call simulation
# --------------------------------------------------------------------------


async def simulate_call(
    call_id: int,
    fixtures: list[bytes],
    turns: int,
    out: LevelResult,
) -> None:
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    limits = httpx.Limits(max_connections=8, max_keepalive_connections=8)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, limits=limits) as client:
        for turn in range(turns):
            pcm = fixtures[turn % len(fixtures)]
            t0 = time.perf_counter()
            try:
                text, stt_ms = await stt_text(client, pcm)
                if not text.strip():
                    text = CALLER_UTTERANCES[turn % len(CALLER_UTTERANCES)]
                history.append({"role": "user", "content": text})

                reply, ttft, llm_ms, tokens = await llm_stream(client, history)
                history.append({"role": "assistant", "content": reply})

                spoken = reply.strip() or "Vâng, tôi đã ghi nhận thông tin."
                _, ttfa = await tts_pcm(client, spoken[:300])
            except Exception as exc:  # noqa: BLE001 - benchmark records failures
                out.errors.append(f"call{call_id}/turn{turn}: {type(exc).__name__}: {exc}")
                continue

            out.samples.append(
                TurnSample(
                    stt_ms=stt_ms,
                    llm_ttft_ms=ttft,
                    llm_total_ms=llm_ms,
                    llm_tokens=tokens,
                    tts_ttfa_ms=ttfa,
                    turn_ms=(time.perf_counter() - t0) * 1000.0,
                )
            )


async def run_level(n: int, fixtures: list[bytes], turns: int) -> LevelResult:
    result = LevelResult(n=n)
    sampler = ResourceSampler()
    sampler.start()
    t0 = time.perf_counter()
    await asyncio.gather(
        *(simulate_call(i, fixtures, turns, result) for i in range(n))
    )
    result.wall_s = time.perf_counter() - t0
    sampler.stop()
    result.res = sampler.snapshot()
    return result


# --------------------------------------------------------------------------
# Setup / warmup
# --------------------------------------------------------------------------


async def build_fixtures() -> list[bytes]:
    """Synthesize the caller utterances once, to replay into STT."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        fixtures = []
        for text in CALLER_UTTERANCES:
            pcm, _ = await tts_pcm(client, text)
            fixtures.append(pcm)
            dur = len(pcm) / 2 / STT_SAMPLE_RATE
            print(f"  fixture: {dur:5.2f}s  {len(pcm):7d} bytes  {text[:44]}…")
        return fixtures


async def warmup(fixtures: list[bytes]) -> None:
    """Pay all cold-start costs before measuring anything."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
        await stt_text(client, fixtures[0])
        await llm_stream(client, [{"role": "user", "content": "Xin chào"}])
        await tts_pcm(client, "Xin chào quý khách.")


async def preflight() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{INFERENCE_URL}/health")
        r.raise_for_status()
        r = await client.get(f"{OLLAMA_URL}/api/tags")
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
        if LLM_MODEL not in names:
            raise SystemExit(f"model {LLM_MODEL} not present in Ollama: {sorted(names)}")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def level_row(r: LevelResult, baseline: LevelResult | None) -> dict[str, Any]:
    turns = [s.turn_ms for s in r.samples]
    resp = [s.response_ms for s in r.samples]
    total_attempts = len(r.samples) + len(r.errors)
    row: dict[str, Any] = {
        "n": r.n,
        "turns_ok": len(r.samples),
        "errors": len(r.errors),
        "error_rate": (len(r.errors) / total_attempts) if total_attempts else 0.0,
        "wall_s": round(r.wall_s, 1),
        "stt": summarize([s.stt_ms for s in r.samples]),
        "llm_ttft": summarize([s.llm_ttft_ms for s in r.samples]),
        "llm_total": summarize([s.llm_total_ms for s in r.samples]),
        "llm_tps": summarize([s.llm_tps for s in r.samples]),
        "tts_ttfa": summarize([s.tts_ttfa_ms for s in r.samples]),
        "response": summarize(resp),
        "turn": summarize(turns),
        "resources": r.res,
    }
    if baseline and baseline.samples:
        base = statistics.fmean([s.response_ms for s in baseline.samples])
        row["response_x_baseline"] = (
            round(statistics.fmean(resp) / base, 2) if resp else float("nan")
        )
    else:
        row["response_x_baseline"] = 1.0
    return row


def verdict(row: dict[str, Any]) -> str:
    if row["error_rate"] > 0:
        return "FAIL (errors)"
    if row["response"]["p95"] > TARGET_TURN_CEILING_MS:
        return "FAIL (> 1500 ms ceiling)"
    if row["response"]["p95"] > TARGET_TURN_P95_MS:
        return "MARGINAL (> 1200 ms p95 target)"
    return "PASS"


def markdown_report(rows: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    def f(v: float) -> str:
        return "—" if v != v else f"{v:.0f}"

    lines = [
        "| N | turns | STT p50/p95 | LLM TTFT p50/p95 | LLM tok/s p50 | TTS p50/p95 |"
        " resp p50/p95 | vs N=1 | CPU mean/max | mem peak | err | verdict |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        res = r["resources"]
        lines.append(
            f"| **{r['n']}** | {r['turns_ok']} "
            f"| {f(r['stt']['p50'])} / {f(r['stt']['p95'])} ms "
            f"| {f(r['llm_ttft']['p50'])} / {f(r['llm_ttft']['p95'])} ms "
            f"| {r['llm_tps']['p50']:.1f} "
            f"| {f(r['tts_ttfa']['p50'])} / {f(r['tts_ttfa']['p95'])} ms "
            f"| **{f(r['response']['p50'])} / {f(r['response']['p95'])} ms** "
            f"| {r['response_x_baseline']}× "
            f"| {res['cpu_mean']}% / {res['cpu_max']}% "
            f"| {res['mem_used_gb_max']} GB "
            f"| {r['errors']} | {verdict(r)} |"
        )
    lines.append("")
    lines.append(f"_Host: {meta['host']} — {meta['ts']}_")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def should_abort(r: LevelResult) -> str | None:
    res = r.res
    total = len(r.samples) + len(r.errors)
    if total and len(r.errors) / total > ABORT_ERROR_RATE:
        return f"error rate {len(r.errors)}/{total} above {ABORT_ERROR_RATE:.0%}"
    if res.get("cpu_sustained_97_s", 0) >= ABORT_CPU_SUSTAIN_S:
        return f"CPU ≥{ABORT_CPU_PCT}% for {res['cpu_sustained_97_s']}s"
    if res.get("mem_pct_max", 0) >= ABORT_MEM_PCT:
        return f"memory {res['mem_pct_max']}% of RAM"
    if res.get("swap_growth_mb_max", 0) >= ABORT_SWAP_GROWTH_MB:
        return f"swap grew {res['swap_growth_mb_max']} MB during this level"
    return None


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--levels", default=",".join(str(n) for n in DEFAULT_LEVELS))
    ap.add_argument("--turns", type=int, default=TURNS_PER_CALL)
    ap.add_argument("--budget", type=float, default=TOTAL_BUDGET_S)
    args = ap.parse_args()
    levels = [int(x) for x in args.levels.split(",") if x.strip()]

    await preflight()
    print(f"host: Apple Silicon, {psutil.cpu_count()} cores, "
          f"{psutil.virtual_memory().total / 1e9:.0f} GB RAM")
    print("building STT fixtures via Piper…")
    fixtures = await build_fixtures()
    print("warming up STT / LLM / TTS…")
    await warmup(fixtures)

    started = time.perf_counter()
    results: list[LevelResult] = []
    rows: list[dict[str, Any]] = []
    stop_reason: str | None = None

    for n in levels:
        elapsed = time.perf_counter() - started
        if elapsed > args.budget:
            stop_reason = f"time budget ({args.budget:.0f}s) exhausted before N={n}"
            print(f"\n!! {stop_reason}")
            break
        print(f"\n=== N={n} concurrent calls × {args.turns} turns ===")
        r = await run_level(n, fixtures, args.turns)
        results.append(r)
        row = level_row(r, results[0] if results else None)
        rows.append(row)
        res = row["resources"]
        print(
            f"  ok={row['turns_ok']} err={row['errors']} wall={row['wall_s']}s\n"
            f"  STT p50 {row['stt']['p50']:.0f}ms | TTFT p50 {row['llm_ttft']['p50']:.0f}ms"
            f" | tok/s {row['llm_tps']['p50']:.1f} | TTS p50 {row['tts_ttfa']['p50']:.0f}ms\n"
            f"  response p50 {row['response']['p50']:.0f}ms p95 {row['response']['p95']:.0f}ms"
            f" -> {verdict(row)}\n"
            f"  CPU {res['cpu_mean']}%/{res['cpu_max']}% "
            f"(inference {res['inference_cpu_mean']}%, ollama {res['ollama_cpu_mean']}%) "
            f"mem {res['mem_used_gb_max']}GB swap {res['swap_mb_max']}MB"
        )
        for e in r.errors[:5]:
            print(f"    ERR {e}")
        reason = should_abort(r)
        if reason:
            stop_reason = f"saturation at N={n}: {reason}"
            print(f"\n!! stopping escalation — {stop_reason}")
            break
        if n != levels[-1]:
            print(f"  cooldown {COOLDOWN_S:.0f}s…")
            await asyncio.sleep(COOLDOWN_S)

    passing = [r["n"] for r in rows if verdict(r) == "PASS"]
    marginal = [r["n"] for r in rows if verdict(r).startswith("MARGINAL")]
    max_ok = max(passing) if passing else 0
    max_marginal = max(marginal) if marginal else 0

    meta = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "host": f"Apple Silicon {psutil.cpu_count()}c / "
                f"{psutil.virtual_memory().total / 1e9:.0f}GB",
        "llm_model": LLM_MODEL,
        "turns_per_call": args.turns,
        "stop_reason": stop_reason,
        "max_concurrent_pass": max_ok,
        "max_concurrent_marginal": max_marginal,
    }

    print("\n" + markdown_report(rows, meta))
    print(f"\nMAX CONCURRENT CALLS (PASS, p95 ≤ {TARGET_TURN_P95_MS:.0f} ms): {max_ok}")
    if max_marginal > max_ok:
        print(f"MAX CONCURRENT (MARGINAL, p95 ≤ {TARGET_TURN_CEILING_MS:.0f} ms): "
              f"{max_marginal}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_DIR / f"concurrency-{stamp}.json"
    out.write_text(json.dumps({"meta": meta, "levels": rows}, indent=2), encoding="utf-8")
    (OUT_DIR / f"concurrency-{stamp}.md").write_text(
        markdown_report(rows, meta), encoding="utf-8"
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
