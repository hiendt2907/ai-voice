"""One-off script to (re)generate golden baseline JSON files.

Run manually (NOT part of the pytest suite) when the FSM-mode behavior is
intentionally changed and the golden baseline must be re-captured:

    cd services/voice
    uv run python -m tests.golden._generate

Requires the voice worker running locally at ws://localhost:8000/ws/call
(uv run uvicorn api.main:app) with the booking_inbound_v1 script reachable
(scripts/examples/booking_inbound_v1.json).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from tests.golden._capture import run_scenario

_HERE = Path(__file__).parent
_SCRIPT_PATH = _HERE / "../../../../scripts/examples/booking_inbound_v1.json"

SCENARIOS: dict[str, list[str]] = {
    # Happy path: full booking flow end to end.
    "happy_path_booking": [
        "tôi muốn đặt lịch khám",
        "ngày mai",
        "buổi sáng lúc 9 giờ",
        "đúng rồi cứ đặt giúp tôi",
        "Nguyễn Văn A",
        "0901234567",
        "đúng rồi",
    ],
    # No-match / reprompt path: first utterance doesn't match anything.
    "no_match_reprompt": [
        "tôi muốn đặt lịch khám",
        "asdkjaskdj lkjaslkdj",  # gibberish -> no match, reprompt
        "ngày mai",
    ],
    # Handoff path: caller asks to check test results -> handoff immediately.
    "handoff_check_result": [
        "tôi muốn tra cứu kết quả xét nghiệm",
    ],
    # Handoff path: caller wants to talk to staff directly.
    "handoff_to_staff": [
        "cho tôi nói chuyện với nhân viên",
    ],
    # Cancel path: caller wants to cancel an appointment -> handoff.
    "handoff_cancel": [
        "tôi muốn hủy lịch hẹn",
    ],
}


async def main() -> None:
    script = json.loads(_SCRIPT_PATH.read_text(encoding="utf-8"))
    out_dir = _HERE
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, utterances in SCENARIOS.items():
        print(f"Capturing scenario: {name} ...")
        call = await run_scenario(
            scenario_name=name,
            script=script,
            caller_utterances=utterances,
            session_id=f"golden-{name}",
        )
        out_path = out_dir / f"{name}.json"
        out_path.write_text(
            json.dumps(call.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  -> {out_path} (end_event={call.final_end_event}, turns={len(call.turns)})")


if __name__ == "__main__":
    asyncio.run(main())
