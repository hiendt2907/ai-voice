from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any, Literal


@dataclass(frozen=True)
class PendingQuestion:
    question_id: str
    question_text: str
    asked_at: float = field(default_factory=time.time)
    timeout_seconds: int = 300


@dataclass(frozen=True)
class TranscriptEntry:
    step_id: str
    role: Literal["agent", "user"]
    text: str
    intent: str | None = None


@dataclass(frozen=True)
class SessionState:
    session_id: str
    script_id: str
    current_step_id: str
    slots: dict[str, str] = field(default_factory=dict)
    no_match_counts: dict[str, int] = field(default_factory=dict)
    status: Literal["active", "handoff", "completed"] = "active"
    transcript: tuple[TranscriptEntry, ...] = field(default_factory=tuple)
    pending_questions: tuple[PendingQuestion, ...] = field(default_factory=tuple)
    emotion_history: tuple[str, ...] = field(default_factory=tuple)

    def with_step(self, step_id: str) -> "SessionState":
        return replace(self, current_step_id=step_id)

    def with_slots(self, new_slots: dict[str, str]) -> "SessionState":
        return replace(self, slots={**self.slots, **new_slots})

    def without_slots(self, keys: list[str]) -> "SessionState":
        return replace(self, slots={k: v for k, v in self.slots.items() if k not in keys})

    def with_status(self, status: Literal["active", "handoff", "completed"]) -> "SessionState":
        return replace(self, status=status)

    def with_transcript_entry(self, entry: TranscriptEntry) -> "SessionState":
        return replace(self, transcript=(*self.transcript, entry))

    def with_pending_question(self, q: PendingQuestion) -> "SessionState":
        return replace(self, pending_questions=(*self.pending_questions, q))

    def without_pending_question(self, question_id: str) -> "SessionState":
        remaining = tuple(q for q in self.pending_questions if q.question_id != question_id)
        return replace(self, pending_questions=remaining)

    def with_emotion(self, label: str, max_keep: int = 5) -> "SessionState":
        trimmed = self.emotion_history[-(max_keep - 1):]
        return replace(self, emotion_history=(*trimmed, label))

    def current_emotion(self) -> str:
        recent = self.emotion_history[-3:]
        if not recent:
            return "neutral"
        return max(set(recent), key=recent.count)

    def increment_no_match(self, step_id: str) -> "SessionState":
        counts = {**self.no_match_counts, step_id: self.no_match_counts.get(step_id, 0) + 1}
        return replace(self, no_match_counts=counts)

    def get_no_match_count(self, step_id: str) -> int:
        return self.no_match_counts.get(step_id, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "script_id": self.script_id,
            "current_step_id": self.current_step_id,
            "slots": dict(self.slots),
            "no_match_counts": dict(self.no_match_counts),
            "status": self.status,
            "pending_questions": [
                {
                    "question_id": q.question_id,
                    "question_text": q.question_text,
                    "asked_at": q.asked_at,
                    "timeout_seconds": q.timeout_seconds,
                }
                for q in self.pending_questions
            ],
            "transcript": [
                {
                    "step_id": e.step_id,
                    "role": e.role,
                    "text": e.text,
                    "intent": e.intent,
                }
                for e in self.transcript
            ],
        }
