"""CLI entry point for the call simulator.

Usage:
    uv run python -m simulator.run_sim --script booking_inbound_v1 \\
        --utterances "tôi muốn đặt lịch" "khám nội khoa" "Nguyễn Văn A" "ngày mai" "buổi sáng" "đúng"

    uv run python -m simulator.run_sim --script /path/to/script.json \\
        --utterances "tôi muốn đặt lịch" --url ws://localhost:8000/ws/call
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from simulator.call_simulator import CallSimulator


def _find_script(name_or_path: str) -> dict:  # type: ignore[type-arg]
    """Load script JSON from a path or from scripts/examples/{name}.json."""
    path = Path(name_or_path)
    if not path.exists():
        # Try relative to the repo root (two levels up from services/voice/)
        here = Path(__file__).parent.parent  # services/voice/
        candidates = [
            here / "../../scripts/examples" / f"{name_or_path}.json",
            here / "../../scripts/examples" / name_or_path,
        ]
        for candidate in candidates:
            if candidate.exists():
                path = candidate
                break
        else:
            print(f"Script not found: {name_or_path!r}", file=sys.stderr)
            print(f"Looked in: {[str(c) for c in candidates]}", file=sys.stderr)
            sys.exit(1)

    with path.open(encoding="utf-8") as f:
        return json.load(f)  # type: ignore[no-any-return]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate a full call against the DoctorCheck voice worker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full booking flow
  uv run python -m simulator.run_sim \\
      --script booking_inbound_v1 \\
      --utterances "tôi muốn đặt lịch" "khám nội khoa" "Nguyễn Văn A" "ngày mai" "buổi sáng" "đúng"

  # Test handoff to staff
  uv run python -m simulator.run_sim \\
      --script booking_inbound_v1 \\
      --utterances "cho tôi nói chuyện với nhân viên"

  # Custom server URL
  uv run python -m simulator.run_sim \\
      --script booking_inbound_v1 \\
      --url ws://localhost:9000/ws/call \\
      --utterances "tôi muốn đặt lịch"
        """,
    )
    parser.add_argument(
        "--script",
        required=True,
        metavar="NAME_OR_PATH",
        help="Script name (e.g. booking_inbound_v1) or path to JSON file",
    )
    parser.add_argument(
        "--utterances",
        nargs="*",
        default=[],
        metavar="TEXT",
        help="Caller utterances in order (space-separated, quote each one)",
    )
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/ws/call",
        help="Voice worker WebSocket URL (default: ws://localhost:8000/ws/call)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Pause between utterances in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--ttfa-warn",
        type=float,
        default=500.0,
        metavar="MS",
        help="TTFA threshold in ms — values above this print in red (default: 500)",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional fixed session ID (generated randomly by default)",
    )
    parser.add_argument(
        "--quiet-timeout",
        type=float,
        default=0.35,
        metavar="SECONDS",
        help="Seconds to wait after last beat before assuming server ready (default: 0.35)",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    script = _find_script(args.script)

    sim = CallSimulator(
        ws_url=args.url,
        utterance_delay_s=args.delay,
        ttfa_warn_ms=args.ttfa_warn,
        quiet_timeout_s=args.quiet_timeout,
    )

    await sim.run(
        script=script,
        caller_utterances=args.utterances,
        session_id=args.session_id,
    )


if __name__ == "__main__":
    asyncio.run(main())
