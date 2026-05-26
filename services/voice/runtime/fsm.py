"""Transition evaluator for the call script FSM.

Supports the condition language used in the call-script contract v0.1:
  - intent == 'X'
  - intent != 'X'
  - slot.NAME != null
  - slot.NAME == null
"""

from __future__ import annotations

import re

# Regex patterns for each condition form
_INTENT_EQ = re.compile(r"^intent\s*==\s*['\"]([^'\"]+)['\"]$")
_INTENT_NEQ = re.compile(r"^intent\s*!=\s*['\"]([^'\"]+)['\"]$")
_SLOT_NOT_NULL = re.compile(r"^slot\.(\w+)\s*!=\s*null$")
_SLOT_IS_NULL = re.compile(r"^slot\.(\w+)\s*==\s*null$")


def evaluate_condition(condition: str, intent: str | None, slots: dict[str, str]) -> bool:
    """Evaluate a single transition condition string."""
    condition = condition.strip()

    if m := _INTENT_EQ.match(condition):
        return intent == m.group(1)

    if m := _INTENT_NEQ.match(condition):
        return intent != m.group(1)

    if m := _SLOT_NOT_NULL.match(condition):
        return slots.get(m.group(1)) is not None

    if m := _SLOT_IS_NULL.match(condition):
        return slots.get(m.group(1)) is None

    # Unknown condition — do not transition
    return False


def resolve_next_step(
    step: dict,
    intent: str | None,
    slots: dict[str, str],
    no_match_count: int,
) -> tuple[str | None, bool]:
    """Return (next_step_id, is_fallback).

    Returns (None, False) when still within reprompt budget (no transition fired).
    Returns (fallback_goto, True) when max_no_match is exceeded.
    """
    transitions: list[dict] = step.get("transitions", [])
    for transition in transitions:
        if evaluate_condition(transition["when"], intent, slots):
            return transition["goto"], False

    # No transition matched
    max_no_match: int = step.get("max_no_match", 3)
    if no_match_count >= max_no_match - 1:
        fallback = step.get("fallback_goto")
        return fallback, True

    return None, False
