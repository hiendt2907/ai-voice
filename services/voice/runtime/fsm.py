"""Transition evaluator for the call script FSM.

Supports the condition language used in the call-script contract v0.1:
  Atoms:
    intent == 'X'
    intent != 'X'
    slot.NAME != null
    slot.NAME == null
    true  (unconditional)
  Compound (evaluated left-to-right):
    <A> && <B>    — both must be true
    <A> || <B>    — either must be true
  Parentheses are stripped before splitting.
"""

from __future__ import annotations

import re

# Regex patterns for each atomic condition form
_INTENT_EQ = re.compile(r"^intent\s*==\s*['\"]([^'\"]+)['\"]$")
_INTENT_NEQ = re.compile(r"^intent\s*!=\s*['\"]([^'\"]+)['\"]$")
_SLOT_NOT_NULL = re.compile(r"^slot\.(\w+)\s*!=\s*null$")
_SLOT_IS_NULL = re.compile(r"^slot\.(\w+)\s*==\s*null$")
_SLOT_VAL_EQ = re.compile(r"^slot\.(\w+)\s*==\s*['\"]([^'\"]+)['\"]$")
_SLOT_VAL_NEQ = re.compile(r"^slot\.(\w+)\s*!=\s*['\"]([^'\"]+)['\"]$")


def _eval_atom(condition: str, intent: str | None, slots: dict[str, str]) -> bool:
    """Evaluate a single atomic condition (no && or ||)."""
    condition = condition.strip().strip("()")

    if condition == "true":
        return True

    if m := _INTENT_EQ.match(condition):
        return intent == m.group(1)

    if m := _INTENT_NEQ.match(condition):
        return intent != m.group(1)

    if m := _SLOT_NOT_NULL.match(condition):
        return slots.get(m.group(1)) is not None

    if m := _SLOT_IS_NULL.match(condition):
        return slots.get(m.group(1)) is None

    if m := _SLOT_VAL_EQ.match(condition):
        return slots.get(m.group(1)) == m.group(2)

    if m := _SLOT_VAL_NEQ.match(condition):
        return slots.get(m.group(1)) != m.group(2)

    # Unknown condition — do not transition
    return False


def evaluate_condition(condition: str, intent: str | None, slots: dict[str, str]) -> bool:
    """Evaluate a transition condition string supporting && and || operators.

    Operator precedence: && binds tighter than ||.
    Simple left-to-right split without a full parser — sufficient for script conditions.
    """
    condition = condition.strip()

    # Split on || first (lowest precedence)
    or_parts = re.split(r"\|\|", condition)
    if len(or_parts) > 1:
        return any(evaluate_condition(part, intent, slots) for part in or_parts)

    # Split on && (higher precedence)
    and_parts = re.split(r"&&", condition)
    if len(and_parts) > 1:
        return all(_eval_atom(part, intent, slots) for part in and_parts)

    return _eval_atom(condition, intent, slots)


_INTENT_EQ_SEARCH = re.compile(r"intent\s*==\s*['\"]([^'\"]+)['\"]")


def extract_step_intents(step: dict) -> list[str]:
    """Return the list of intents accepted by this step's transitions."""
    intents: list[str] = []
    for t in step.get("transitions", []):
        when = t.get("when", "")
        for m in _INTENT_EQ_SEARCH.finditer(when):
            intent = m.group(1)
            if intent not in intents:
                intents.append(intent)
    return intents


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
