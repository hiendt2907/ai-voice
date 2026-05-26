from dataclasses import dataclass
from typing import Any

PAUSE_DURATION_MS: dict[str, int] = {
    "none": 0,
    "micro": 80,
    "short": 150,
    "breath": 250,
    "medium": 400,
    "long": 700,
    "turn": 1000,
}


@dataclass
class ProsodyChunk:
    text: str
    pause_after_ms: int
    role: str


def beats_to_chunks(beats: list[dict[str, Any]]) -> list[ProsodyChunk]:
    return [
        ProsodyChunk(
            text=beat["text"],
            pause_after_ms=PAUSE_DURATION_MS.get(beat.get("pause_after", "none"), 0),
            role=beat.get("role", "agent"),
        )
        for beat in beats
    ]
