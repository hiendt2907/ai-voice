"""CallSimulator — async WebSocket client that emulates CloudFone gateway.

Connects to the voice worker WS endpoint, sends START + UTTERANCE events,
and prints agent beats with timing information.

Two run modes:
  • run(script, utterances)          — mock text utterances (CI/testing)
  • run_with_audio(script, wav_path) — real audio_frame events from WAV file
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import websockets

from audio.codec import pcm_to_ulaw
from cloudfone.protocol import InboundEvent, OutboundEvent

# ANSI color codes
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_TTFA_WARN_DEFAULT_MS = 500.0
_QUIET_TIMEOUT_S = 0.35  # wait this long after last beat before assuming server is ready


@dataclass
class TurnRecord:
    turn: int
    role: str  # "agent" | "user"
    text: str
    step_id: str = ""
    ttfa_ms: float | None = None


@dataclass
class SimResult:
    session_id: str
    end_reason: str  # "hangup" | "handoff" | "disconnect" | "utterances_exhausted"
    end_step_id: str = ""
    turns: list[TurnRecord] = field(default_factory=list)

    @property
    def agent_turns(self) -> list[TurnRecord]:
        return [t for t in self.turns if t.role == "agent"]

    @property
    def user_turns(self) -> list[TurnRecord]:
        return [t for t in self.turns if t.role == "user"]


class CallSimulator:
    """Emulates CloudFone gateway — drives a full call via the voice worker WS API."""

    def __init__(
        self,
        ws_url: str = "ws://localhost:8000/ws/call",
        utterance_delay_s: float = 1.0,
        ttfa_warn_ms: float = _TTFA_WARN_DEFAULT_MS,
        quiet_timeout_s: float = _QUIET_TIMEOUT_S,
        verbose: bool = True,
    ) -> None:
        self.ws_url = ws_url
        self.utterance_delay_s = utterance_delay_s
        self.ttfa_warn_ms = ttfa_warn_ms
        self.quiet_timeout_s = quiet_timeout_s
        self.verbose = verbose

    async def run(
        self,
        script: dict[str, Any],
        caller_utterances: list[str],
        session_id: str | None = None,
    ) -> SimResult:
        sid = session_id or str(uuid.uuid4())
        turns: list[TurnRecord] = []

        if self.verbose:
            print(f"\n{_BOLD}{'─' * 60}{_RESET}")
            print(f"{_BOLD}  DoctorCheck Call Simulator{_RESET}")
            print(f"{_BOLD}{'─' * 60}{_RESET}")
            print(f"  Session : {_DIM}{sid}{_RESET}")
            print(f"  Server  : {_DIM}{self.ws_url}{_RESET}")
            print(f"  Script  : {_DIM}{script.get('id', '?')}{_RESET}")
            print(f"{_BOLD}{'─' * 60}{_RESET}\n")

        try:
            async with websockets.connect(self.ws_url) as ws:
                # ── 1. Send START ──────────────────────────────────────────
                start_msg: dict[str, Any] = {
                    "event": InboundEvent.START,
                    "session_id": sid,
                    "campaign_id": script.get("campaign_id"),
                    "script_version_id": script.get("id"),
                    "direction": script.get("direction", "inbound"),
                    "caller_number": "+84901234567",
                    "caller_number_masked": "+849012****67",
                    "script": script,
                }
                t_sent = time.perf_counter()
                await ws.send(json.dumps(start_msg))

                # ── 2. Collect greeting beats ──────────────────────────────
                beats, end_event, end_step = await self._collect_response(ws, t_sent)
                agent_turn = self._record_agent_turn(0, beats)
                turns.append(agent_turn)

                if end_event:
                    result = SimResult(sid, end_event, end_step, turns)
                    if self.verbose:
                        self._print_summary(result)
                    return result

                # ── 3. Drive utterances ────────────────────────────────────
                for i, utterance in enumerate(caller_utterances, start=1):
                    await asyncio.sleep(self.utterance_delay_s)

                    user_turn = TurnRecord(turn=i, role="user", text=utterance)
                    turns.append(user_turn)
                    if self.verbose:
                        self._print_user_utterance(utterance, i)

                    utt_msg: dict[str, Any] = {
                        "event": InboundEvent.UTTERANCE,
                        "text": utterance,
                        "confidence": 1.0,
                    }
                    t_sent = time.perf_counter()
                    await ws.send(json.dumps(utt_msg))

                    beats, end_event, end_step = await self._collect_response(ws, t_sent)
                    agent_turn = self._record_agent_turn(i, beats)
                    turns.append(agent_turn)

                    if end_event:
                        result = SimResult(sid, end_event, end_step, turns)
                        if self.verbose:
                            self._print_summary(result)
                        return result

                # ── 4. No more utterances → hang up ───────────────────────
                await ws.send(json.dumps({"event": InboundEvent.HANGUP}))
                end_reason = "utterances_exhausted"

        except websockets.exceptions.ConnectionClosed:
            end_reason = "disconnect"
        except OSError as exc:
            print(f"\n{_RED}Connection failed: {exc}{_RESET}")
            print(f"{_DIM}Is the voice worker running? uv run uvicorn api.main:app{_RESET}\n")
            return SimResult(sid, "connect_error", "", turns)

        result = SimResult(sid, end_reason, "", turns)
        if self.verbose:
            self._print_summary(result)
        return result

    async def run_with_audio(
        self,
        script: dict[str, Any],
        wav_path: str | Path,
        session_id: str | None = None,
        frame_ms: int = 20,
    ) -> SimResult:
        """Run simulator in real audio mode — reads WAV, sends audio_frame events.

        The WAV file must be mono PCM (any sample rate; resampled to 8kHz if needed).
        Frames are sent at real-time pace (frame_ms interval).
        """
        sid = session_id or str(uuid.uuid4())
        turns: list[TurnRecord] = []

        audio_frames = _load_wav_as_ulaw_frames(wav_path, frame_ms=frame_ms)

        if self.verbose:
            print(f"\n{_BOLD}{'─' * 60}{_RESET}")
            print(f"{_BOLD}  DoctorCheck Call Simulator (audio mode){_RESET}")
            print(f"{_BOLD}{'─' * 60}{_RESET}")
            print(f"  Session : {_DIM}{sid}{_RESET}")
            print(f"  Server  : {_DIM}{self.ws_url}{_RESET}")
            print(f"  WAV     : {_DIM}{wav_path}{_RESET}")
            print(f"  Frames  : {_DIM}{len(audio_frames)} × {frame_ms}ms{_RESET}")
            print(f"{_BOLD}{'─' * 60}{_RESET}\n")

        try:
            async with websockets.connect(self.ws_url) as ws:
                # 1. Send START
                start_msg: dict[str, Any] = {
                    "event": InboundEvent.START,
                    "session_id": sid,
                    "campaign_id": script.get("campaign_id"),
                    "script_version_id": script.get("id"),
                    "direction": script.get("direction", "inbound"),
                    "caller_number": "+84901234567",
                    "caller_number_masked": "+849012****67",
                    "script": script,
                }
                t_sent = time.perf_counter()
                await ws.send(json.dumps(start_msg))

                # 2. Collect greeting
                beats, end_event, end_step = await self._collect_response(ws, t_sent)
                turns.append(self._record_agent_turn(0, beats))
                if end_event:
                    result = SimResult(sid, end_event, end_step, turns)
                    if self.verbose:
                        self._print_summary(result)
                    return result

                # 3. Stream audio frames
                for i, frame_b64 in enumerate(audio_frames):
                    await asyncio.sleep(frame_ms / 1000.0)
                    frame_msg = {
                        "event": InboundEvent.AUDIO_FRAME,
                        "data": frame_b64,
                        "seq": i,
                    }
                    await ws.send(json.dumps(frame_msg))

                    # Check for any completed agent response (non-blocking)
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=0.01)
                        msg: dict[str, Any] = json.loads(raw)
                        if msg.get("event") in (OutboundEvent.HANGUP, OutboundEvent.HANDOFF):
                            end_event = msg["event"]
                            end_step = msg.get("step_id", "")
                            break
                    except asyncio.TimeoutError:
                        pass

                # 4. Hangup
                if not end_event:
                    await ws.send(json.dumps({"event": InboundEvent.HANGUP}))
                    # Collect any final response
                    beats, end_event, end_step = await self._collect_response(
                        ws, time.perf_counter()
                    )
                    turns.append(self._record_agent_turn(len(turns), beats))
                    end_event = end_event or "utterances_exhausted"

        except websockets.exceptions.ConnectionClosed:
            end_event = "disconnect"
        except OSError as exc:
            print(f"\n{_RED}Connection failed: {exc}{_RESET}")
            return SimResult(sid, "connect_error", "", turns)

        result = SimResult(sid, end_event or "utterances_exhausted", end_step, turns)
        if self.verbose:
            self._print_summary(result)
        return result

    async def _collect_response(
        self,
        ws: Any,
        t_sent: float,
    ) -> tuple[list[dict[str, Any]], str | None, str]:
        """Collect beats until server goes quiet (quiet_timeout_s with no new message).

        Returns (beats, terminal_event_or_None, step_id).
        """
        beats: list[dict[str, Any]] = []
        end_event: str | None = None
        end_step: str = ""
        first_beat = True

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=self.quiet_timeout_s)
            except asyncio.TimeoutError:
                break  # server is quiet → step complete, awaiting next utterance

            msg: dict[str, Any] = json.loads(raw)
            event = msg.get("event", "")

            if event == OutboundEvent.BEAT:
                if first_beat:
                    ttfa_ms = msg.get("ttfa_ms") or round((time.perf_counter() - t_sent) * 1000, 1)
                    msg = {**msg, "_ttfa_ms": ttfa_ms}
                    first_beat = False
                    if self.verbose:
                        self._print_agent_beat(msg, ttfa_ms)
                else:
                    if self.verbose:
                        self._print_agent_beat(msg)
                beats.append(msg)

            elif event == OutboundEvent.AUDIO_CHUNK:
                # Real TTS mode — measure TTFA from chunk timing
                if first_beat:
                    ttfa_ms = round((time.perf_counter() - t_sent) * 1000, 1)
                    first_beat = False
                    if self.verbose:
                        color = _RED if ttfa_ms > self.ttfa_warn_ms else _GREEN
                        print(f"  {_DIM}[audio chunk received]{_RESET}  TTFA {color}{ttfa_ms:.0f}ms{_RESET}")
                beats.append(msg)

            elif event == OutboundEvent.HANGUP:
                end_event = "hangup"
                end_step = msg.get("step_id", "")
                if self.verbose:
                    print(f"\n  {_MAGENTA}{_BOLD}[HANGUP]{_RESET}{_MAGENTA} step={end_step}{_RESET}")
                break

            elif event == OutboundEvent.HANDOFF:
                end_event = "handoff"
                end_step = msg.get("step_id", "")
                reason = msg.get("reason", "")
                if self.verbose:
                    print(f"\n  {_MAGENTA}{_BOLD}[HANDOFF]{_RESET}{_MAGENTA} step={end_step} reason={reason}{_RESET}")
                break

        return beats, end_event, end_step

    def _record_agent_turn(self, turn: int, beats: list[dict[str, Any]]) -> TurnRecord:
        texts = [b.get("text", "") for b in beats if b.get("event") == OutboundEvent.BEAT]
        text = " ".join(t for t in texts if t)
        ttfa = next((b.get("_ttfa_ms") for b in beats if "_ttfa_ms" in b), None)
        step_id = next((b.get("step_id", "") for b in beats if "step_id" in b), "")
        return TurnRecord(turn=turn, role="agent", text=text, step_id=step_id, ttfa_ms=ttfa)

    def _print_agent_beat(self, msg: dict[str, Any], ttfa_ms: float | None = None) -> None:
        text = msg.get("text", "")
        pause_ms = msg.get("pause_ms", 0)
        step_id = msg.get("step_id", "")
        turn = msg.get("turn", 0)

        ttfa_str = ""
        if ttfa_ms is not None:
            color = _RED if ttfa_ms > self.ttfa_warn_ms else _GREEN
            ttfa_str = f"  {color}TTFA {ttfa_ms:.0f}ms{_RESET}"

        pause_str = f"{_DIM}[{pause_ms}ms]{_RESET}" if pause_ms else ""
        print(f"  {_CYAN}[AGENT t{turn}]{_RESET} {text} {pause_str}{ttfa_str}")

    def _print_user_utterance(self, text: str, turn: int) -> None:
        print(f"\n  {_YELLOW}[USER  t{turn}]{_RESET} {_BOLD}{text}{_RESET}")

    def _print_summary(self, result: SimResult) -> None:
        print(f"\n{_BOLD}{'─' * 60}{_RESET}")
        print(f"{_BOLD}  Call Summary — {result.end_reason.upper()}{_RESET}")
        print(f"{_BOLD}{'─' * 60}{_RESET}")
        print(f"  End step : {result.end_step_id or '—'}")
        print(f"  Turns    : {len(result.turns)} ({len(result.agent_turns)} agent, {len(result.user_turns)} user)")

        agent_turns_with_ttfa = [t for t in result.agent_turns if t.ttfa_ms is not None]
        if agent_turns_with_ttfa:
            ttfas = [t.ttfa_ms for t in agent_turns_with_ttfa]  # type: ignore[misc]
            avg_ttfa = sum(ttfas) / len(ttfas)
            max_ttfa = max(ttfas)
            ttfa_color = _RED if max_ttfa > self.ttfa_warn_ms else _GREEN
            print(f"  TTFA avg : {ttfa_color}{avg_ttfa:.0f}ms{_RESET}  max {ttfa_color}{max_ttfa:.0f}ms{_RESET}")

        print(f"\n  {_BOLD}Transcript:{_RESET}")
        for t in result.turns:
            if t.role == "agent":
                if t.text:
                    print(f"    {_CYAN}AI :{_RESET} {t.text}")
            else:
                print(f"    {_YELLOW}You:{_RESET} {t.text}")
        print(f"{_BOLD}{'─' * 60}{_RESET}\n")


# ── WAV → μ-law frames helper ─────────────────────────────────────────────────

def _load_wav_as_ulaw_frames(wav_path: str | Path, frame_ms: int = 20) -> list[str]:
    """Load a WAV file and convert to list of base64-encoded μ-law frames at 8kHz.

    Resamples to 8kHz mono if needed (requires scipy).
    Returns list of base64 strings, one per frame_ms interval.
    """
    with wave.open(str(wav_path), "rb") as wf:
        src_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    dtype = np.int16 if sampwidth == 2 else np.int8
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    # Convert stereo to mono
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    # Resample to 8kHz if needed
    target_rate = 8000
    if src_rate != target_rate:
        try:
            from math import gcd  # noqa: PLC0415

            from scipy.signal import resample_poly  # noqa: PLC0415

            g = gcd(src_rate, target_rate)
            samples = resample_poly(samples, target_rate // g, src_rate // g).astype(np.float32)
        except ImportError:
            ratio = target_rate / src_rate
            new_len = int(len(samples) * ratio)
            indices = np.linspace(0, len(samples) - 1, new_len)
            samples = np.interp(indices, np.arange(len(samples)), samples).astype(np.float32)

    # Normalize to [-1, 1] if needed, then convert to int16
    max_val = np.abs(samples).max()
    if max_val > 1.0:
        samples = samples / max_val
    pcm_int16 = (samples * 32767).astype(np.int16)

    # Chunk into frames and encode to μ-law
    frame_samples = int(target_rate * frame_ms / 1000)
    frames: list[str] = []
    for i in range(0, len(pcm_int16), frame_samples):
        chunk = pcm_int16[i : i + frame_samples]
        if len(chunk) < frame_samples:
            chunk = np.pad(chunk, (0, frame_samples - len(chunk)))
        ulaw_bytes = pcm_to_ulaw(chunk)
        frames.append(base64.b64encode(ulaw_bytes).decode())

    return frames
