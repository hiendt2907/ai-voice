"""Filler word pools for Vietnamese AI call agent.

Fillers are short utterances played immediately after speech detection to
reduce perceived latency while processing is happening concurrently.

Anti-repetition: FillerSelector rotates through the pool, never repeating
the same filler twice in a row.

Context types:
  thinking   — very short, while STT+intent finishes (<300ms processing)
  ack        — acknowledgment when intent matched with no slot fill
  wait       — generic wait (longer processing)
  checking   — actively looking up data (API call in progress)
  confirming — confirming/booking action in progress
  ack_slot   — echo back the slot value just heard (use value= param)
"""

from __future__ import annotations

from typing import Literal

ContextType = Literal["thinking", "ack", "wait", "checking", "confirming", "ack_slot"]

_POOLS: dict[ContextType, list[str]] = {
    "thinking": [
        "Dạ,",
        "Vâng,",
        "À,",
        "Ừm,",
    ],
    "ack": [
        "Dạ vâng ạ.",
        "Được ạ.",
        "Vâng ạ.",
        "Dạ em hiểu ạ.",
    ],
    "wait": [
        "Dạ, bác đợi em một chút ạ.",
        "Em xem ngay ạ.",
        "Để em kiểm tra lại ạ.",
    ],
    "checking": [
        "Dạ, để em kiểm tra lịch cho anh/chị nhé...",
        "Vâng, em xem ngay ạ...",
        "Dạ, cho em một chút ạ...",
        "Để em kiểm tra trong hệ thống nhé...",
    ],
    "confirming": [
        "Vâng, để em xác nhận lại thông tin ạ...",
        "Dạ, em kiểm tra hệ thống một chút ạ...",
        "Để em đặt lịch cho anh/chị ạ...",
    ],
    "ack_slot": [
        "Vâng, {value} ạ.",
        "Dạ, {value} ạ.",
        "À, {value} ạ.",
    ],
}


class FillerSelector:
    """Stateful filler selector with anti-repetition."""

    def __init__(self) -> None:
        self._last: dict[ContextType, str] = {}
        self._indices: dict[str, int] = {k: 0 for k in _POOLS}

    def next(self, context: ContextType = "thinking", value: str = "") -> str:
        """Return next filler for the given context.

        Args:
            context: Which pool to draw from.
            value: For ack_slot context, the slot value to echo back.
        """
        pool = _POOLS[context]
        last = self._last.get(context)
        idx = self._indices.get(context, 0)

        for _ in range(len(pool)):
            candidate = pool[idx % len(pool)]
            idx += 1
            if candidate != last:
                self._indices[context] = idx
                self._last[context] = candidate
                result = candidate.replace("{value}", value) if value else candidate
                return result

        # All identical (shouldn't happen with pool size ≥ 2)
        result = pool[0].replace("{value}", value) if value else pool[0]
        return result
