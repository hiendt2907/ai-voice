"""The per-turn decision record — one object, three destinations.

The same trace is emitted as OTel span attributes (Tempo), pushed over the
call WebSocket as a `turn_trace` event (live view), and persisted into
`call_turns.metadata` on hangup (post-call review in Portal). Keeping one
structure for all three is what stops the three views from disagreeing.

It answers "why did the agent say that?": what STT heard and how sure it
was, which NLU tier resolved the intent, whether RAG found grounding,
whether a guardrail blocked the turn, where the FSM moved, and what each
stage cost in time and tokens.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageTiming:
    """Wall-clock for one stage, in ms. Started on enter, closed on exit."""

    name: str
    started_at: float = field(default_factory=time.perf_counter)
    duration_ms: float | None = None

    def close(self) -> float:
        self.duration_ms = round((time.perf_counter() - self.started_at) * 1000, 1)
        return self.duration_ms


@dataclass
class TurnTrace:
    """Decision record for a single caller turn."""

    turn: int
    session_id: str = ""
    trace_id: str = ""

    # ── what the caller said ────────────────────────────────────────────
    stt_text: str = ""
    stt_confidence: float | None = None
    stt_engine: str = ""
    stt_ms: float | None = None

    # ── how it was understood ───────────────────────────────────────────
    # nlu_tier is the tier that actually produced the result: "vector" (a
    # local embedding lookup) or "llm" (the stateful resolver). llm_used
    # records whether the slow path ran at all, which is the number to watch
    # when tuning the NLU dataset.
    nlu_tier: str = ""
    nlu_intent: str | None = None
    nlu_confidence: float | None = None
    nlu_llm_used: bool = False
    nlu_ms: float | None = None

    # ── grounding ───────────────────────────────────────────────────────
    rag_hit: bool = False
    rag_article_id: str | None = None
    rag_article_title: str | None = None
    rag_score: float | None = None
    rag_ms: float | None = None

    # ── safety ──────────────────────────────────────────────────────────
    guardrail_blocked: bool = False
    guardrail_reason: str | None = None

    # ── free-form reasoning (tier 4) ────────────────────────────────────
    llm_model: str | None = None
    llm_prompt_tokens: int | None = None
    llm_completion_tokens: int | None = None
    llm_refused: bool = False
    llm_ms: float | None = None

    # ── where the conversation went ─────────────────────────────────────
    step_from: str = ""
    step_to: str = ""
    slots_new: dict[str, str] = field(default_factory=dict)
    escalated: bool = False

    # ── what the agent said back ────────────────────────────────────────
    agent_text: str = ""
    tts_engine: str = ""
    tts_ttfa_ms: float | None = None
    tts_chars: int | None = None

    # ── audio artefacts (object storage keys, not bytes) ────────────────
    caller_audio_key: str | None = None
    agent_audio_key: str | None = None

    total_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Flat dict for the WS event and for call_turns.metadata."""
        return {
            "turn": self.turn,
            "trace_id": self.trace_id,
            "stt": {
                "text": self.stt_text,
                "confidence": self.stt_confidence,
                "engine": self.stt_engine,
                "ms": self.stt_ms,
            },
            "nlu": {
                "tier": self.nlu_tier,
                "intent": self.nlu_intent,
                "confidence": self.nlu_confidence,
                "llm_used": self.nlu_llm_used,
                "ms": self.nlu_ms,
            },
            "rag": {
                "hit": self.rag_hit,
                "article_id": self.rag_article_id,
                "article_title": self.rag_article_title,
                "score": self.rag_score,
                "ms": self.rag_ms,
            },
            "guardrail": {
                "blocked": self.guardrail_blocked,
                "reason": self.guardrail_reason,
            },
            "llm": {
                "model": self.llm_model,
                "prompt_tokens": self.llm_prompt_tokens,
                "completion_tokens": self.llm_completion_tokens,
                "refused": self.llm_refused,
                "ms": self.llm_ms,
            },
            "routing": {
                "step_from": self.step_from,
                "step_to": self.step_to,
                "slots_new": self.slots_new,
                "escalated": self.escalated,
            },
            "agent": {
                "text": self.agent_text,
                "tts_engine": self.tts_engine,
                "ttfa_ms": self.tts_ttfa_ms,
                "chars": self.tts_chars,
            },
            "audio": {
                "caller_key": self.caller_audio_key,
                "agent_key": self.agent_audio_key,
            },
            "total_ms": self.total_ms,
        }

    def apply_to_span(self, sp: Any) -> None:
        """Copy the flat, queryable fields onto an OTel span.

        Only scalars — Tempo indexes attributes for search, and nested dicts
        aren't searchable. slots_new is joined into a key list so a trace can
        still be found by "which turn filled appointment_date".
        """
        from obs.tracing import set_attr  # noqa: PLC0415

        set_attr(sp, "turn", self.turn)
        set_attr(sp, "stt.text", self.stt_text)
        set_attr(sp, "stt.confidence", self.stt_confidence)
        set_attr(sp, "stt.engine", self.stt_engine)
        set_attr(sp, "nlu.tier", self.nlu_tier)
        set_attr(sp, "nlu.intent", self.nlu_intent)
        set_attr(sp, "nlu.confidence", self.nlu_confidence)
        set_attr(sp, "nlu.llm_used", self.nlu_llm_used)
        set_attr(sp, "rag.hit", self.rag_hit)
        set_attr(sp, "rag.article_title", self.rag_article_title)
        set_attr(sp, "rag.score", self.rag_score)
        set_attr(sp, "guardrail.blocked", self.guardrail_blocked)
        set_attr(sp, "guardrail.reason", self.guardrail_reason)
        set_attr(sp, "llm.model", self.llm_model)
        set_attr(sp, "llm.prompt_tokens", self.llm_prompt_tokens)
        set_attr(sp, "llm.completion_tokens", self.llm_completion_tokens)
        set_attr(sp, "llm.refused", self.llm_refused)
        set_attr(sp, "routing.step_from", self.step_from)
        set_attr(sp, "routing.step_to", self.step_to)
        set_attr(sp, "routing.slots_new", ",".join(sorted(self.slots_new)))
        set_attr(sp, "routing.escalated", self.escalated)
        set_attr(sp, "agent.text", self.agent_text)
        set_attr(sp, "agent.tts_engine", self.tts_engine)
        set_attr(sp, "agent.ttfa_ms", self.tts_ttfa_ms)
        set_attr(sp, "total_ms", self.total_ms)
