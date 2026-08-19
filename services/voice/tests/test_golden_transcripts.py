"""Golden-transcript regression test for Phase 1 ws.py -> call/ extraction.

This is the safety net required before refactoring `api/routers/ws.py`
(see docs/ai-streaming-voice-architecture-proposal.md, section G, Phase 1).

It replays the exact same scripted calls used to capture
`tests/golden/*.json` against a REAL, RUNNING voice worker over the real
`/ws/call` WebSocket endpoint (mock UTTERANCE mode, TTS disabled via
`use_real_tts: false` for determinism/speed), and asserts the important
observable-over-the-wire fields are unchanged:

  - per-turn agent response text
  - per-turn step_id(s) touched
  - turn_meta: intent, slots_new, step_from, step_to
  - terminal event (hangup/handoff) and its step_id

It deliberately does NOT compare audio bytes (non-deterministic across TTS
engine swaps) or timing (TTFA, latency).

Requires the voice worker to be reachable at ws://localhost:8000/ws/call
(same infra dependencies as `simulator/run_sim.py`: Postgres + Redis for
script/KB/NLU export, and whatever NLU classifier is configured). If the
worker isn't reachable, tests are skipped rather than failed, since this is
an integration test against live infra, not a unit test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.golden._capture import run_scenario

pytestmark = pytest.mark.golden

_GOLDEN_DIR = Path(__file__).parent / "golden"
_SCRIPT_PATH = _GOLDEN_DIR / "../../../../scripts/examples/booking_inbound_v1.json"
_WS_URL = "ws://localhost:8000/ws/call"

# Mirrors tests/golden/_generate.py SCENARIOS — kept in sync manually since
# the captured JSON baseline must exist for each name listed here.
SCENARIOS: dict[str, list[str]] = {
    "happy_path_booking": [
        "tôi muốn đặt lịch khám",
        "ngày mai",
        "buổi sáng lúc 9 giờ",
        "đúng rồi cứ đặt giúp tôi",
        "Nguyễn Văn A",
        "0901234567",
        "đúng rồi",
    ],
    "no_match_reprompt": [
        "tôi muốn đặt lịch khám",
        "asdkjaskdj lkjaslkdj",
        "ngày mai",
    ],
    "handoff_check_result": ["tôi muốn tra cứu kết quả xét nghiệm"],
    "handoff_to_staff": ["cho tôi nói chuyện với nhân viên"],
    "handoff_cancel": ["tôi muốn hủy lịch hẹn"],
}


def _worker_reachable() -> bool:
    import socket

    try:
        with socket.create_connection(("localhost", 8000), timeout=1.0):
            return True
    except OSError:
        return False


def _load_baseline(scenario: str) -> dict:
    path = _GOLDEN_DIR / f"{scenario}.json"
    if not path.exists():
        pytest.skip(f"No golden baseline captured for {scenario!r} — run tests/golden/_generate.py")
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_turn_matches(expected: dict, actual: dict, scenario: str, idx: int) -> None:
    ctx = f"scenario={scenario} turn={idx}"
    assert expected["caller_utterance"] == actual["caller_utterance"], ctx
    assert expected["agent_text"] == actual["agent_text"], f"{ctx}: agent_text mismatch"
    assert expected["step_ids"] == actual["step_ids"], f"{ctx}: step_ids mismatch"
    assert expected["end_event"] == actual["end_event"], f"{ctx}: end_event mismatch"
    assert expected["end_step_id"] == actual["end_step_id"], f"{ctx}: end_step_id mismatch"

    exp_meta = expected["turn_meta"]
    act_meta = actual["turn_meta"]
    if exp_meta is None:
        assert act_meta is None, f"{ctx}: expected no turn_meta, got {act_meta}"
        return
    assert act_meta is not None, f"{ctx}: expected turn_meta, got None"
    assert exp_meta["intent"] == act_meta["intent"], f"{ctx}: intent mismatch"
    assert exp_meta["slots_new"] == act_meta["slots_new"], f"{ctx}: slots_new mismatch"
    assert exp_meta["step_from"] == act_meta["step_from"], f"{ctx}: step_from mismatch"
    assert exp_meta["step_to"] == act_meta["step_to"], f"{ctx}: step_to mismatch"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", sorted(SCENARIOS.keys()))
async def test_golden_transcript_matches_baseline(scenario: str) -> None:
    if not _worker_reachable():
        pytest.skip("voice worker not reachable at localhost:8000 — start it to run golden tests")
    if not _SCRIPT_PATH.exists():
        pytest.skip("booking_inbound_v1.json example script not found")

    baseline = _load_baseline(scenario)
    script = json.loads(_SCRIPT_PATH.read_text(encoding="utf-8"))

    actual = await run_scenario(
        scenario_name=scenario,
        script=script,
        caller_utterances=SCENARIOS[scenario],
        ws_url=_WS_URL,
        session_id=f"golden-replay-{scenario}",
    )
    actual_dict = actual.to_dict()

    assert len(baseline["turns"]) == len(actual_dict["turns"]), (
        f"scenario={scenario}: turn count mismatch "
        f"(baseline={len(baseline['turns'])}, actual={len(actual_dict['turns'])})"
    )
    for idx, (exp_turn, act_turn) in enumerate(zip(baseline["turns"], actual_dict["turns"])):
        _assert_turn_matches(exp_turn, act_turn, scenario, idx)

    assert baseline["final_end_event"] == actual_dict["final_end_event"], (
        f"scenario={scenario}: final_end_event mismatch"
    )
    assert baseline["final_end_step_id"] == actual_dict["final_end_step_id"], (
        f"scenario={scenario}: final_end_step_id mismatch"
    )
