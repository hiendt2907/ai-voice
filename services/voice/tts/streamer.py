"""Streaming TTS beat renderer.

Yields BeatPayload events one at a time — caller can send each beat to the
WS client before the next beat is synthesised. Enables TTFA < 400ms.
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncGenerator

from cloudfone.protocol import BeatPayload
from tts.prosody import PAUSE_DURATION_MS, beats_to_chunks

_TEMPLATE_VAR = re.compile(r"\{\{(\w+)\}\}")


def _render_text(text: str, slots: dict[str, str]) -> str:
    return _TEMPLATE_VAR.sub(lambda m: slots.get(m.group(1), m.group(0)), text)


async def stream_step_beats(
    step: dict,
    slots: dict[str, str],
    no_match_count: int,
    turn: int,
    t_start: float | None = None,
) -> AsyncGenerator[BeatPayload, None]:
    """Yield one BeatPayload per beat, measuring TTFA on the first beat."""
    # Choose variant
    if no_match_count > 0 and step.get("reprompt_variants"):
        reprompts: list[dict] = step["reprompt_variants"]
        idx = (no_match_count - 1) % len(reprompts)
        variant = reprompts[idx]
    else:
        variants: list[dict] = step.get("variants", [])
        variant = variants[0] if variants else {}

    beats: list[dict] = variant.get("beats", [])
    if t_start is None:
        t_start = time.perf_counter()

    first = True
    for beat in beats:
        raw_text: str = beat.get("text", "")
        rendered = _render_text(raw_text, slots)
        pause_tier: str = beat.get("pause_after", "none")
        pause_ms = PAUSE_DURATION_MS.get(pause_tier, 0)

        ttfa: float | None = None
        if first:
            ttfa = (time.perf_counter() - t_start) * 1000
            first = False

        yield BeatPayload(
            text=rendered,
            pause_ms=pause_ms,
            turn=turn,
            step_id=str(step.get("id", "")),
            ttfa_ms=ttfa,
        )
