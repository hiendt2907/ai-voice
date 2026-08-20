"""Entrypoint: register the SIP softphone with voip24h and bridge every
answered call to the AI pipeline over CloudFone WS. Runs on the Macbook
only — voip24h blocks the GCP IP, see sip/client.py's module docstring.

Usage:
    uv run python -m sip.run_softphone \\
        --sip-server 222.255.115.80 --sip-user 642 --sip-password '...' \\
        --ws-url ws://127.0.0.1:8000/ws/call \\
        --script scripts/examples/booking_inbound_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket
from pathlib import Path

from sip.client import SipCall, SipPhone
from sip.cloudfone_bridge import bridge_call

logger = logging.getLogger(__name__)


def _detect_local_ip(probe_host: str, probe_port: int) -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((probe_host, probe_port))
        return s.getsockname()[0]
    finally:
        s.close()


async def _run(args: argparse.Namespace) -> None:
    script = json.loads(Path(args.script).read_text(encoding="utf-8"))
    my_ip = args.my_ip or _detect_local_ip(args.sip_server, args.sip_port)
    logger.info("Local IP for SIP/RTP: %s", my_ip)

    async def on_call_start(call: SipCall) -> None:
        logger.info("Call answered: caller=%s — bridging to %s", call.caller_number, args.ws_url)
        if args.pre_roll_s > 0:
            # voip24h answers our SIP leg at machine speed, but the actual
            # PSTN bridge to the human's phone can take several seconds
            # longer to come up — starting the AI's greeting immediately
            # plays it into dead air. Wait before opening the bridge (which
            # triggers the greeting on connect); this doesn't delay
            # capturing the caller's audio, since there's nothing real to
            # capture until the human leg is actually up either.
            logger.info("Pre-roll: waiting %.1fs for voip24h's PSTN bridge", args.pre_roll_s)
            await asyncio.sleep(args.pre_roll_s)
        try:
            await bridge_call(call, args.ws_url, script, campaign_id=args.campaign_id)
        except Exception:
            logger.exception("Bridge failed for call %s", call.call_id)

    async def on_call_end(call_id: str) -> None:
        logger.info("Call ended: %s", call_id)

    phone = SipPhone(
        server=args.sip_server,
        port=args.sip_port,
        username=args.sip_user,
        password=args.sip_password,
        my_ip=my_ip,
        sip_port=args.local_sip_port,
        rtp_port_low=args.rtp_port_low,
        rtp_port_high=args.rtp_port_high,
        on_call_start=on_call_start,
        on_call_end=on_call_end,
    )
    await phone.start()
    logger.info("SIP softphone registered — waiting for calls (Ctrl+C to stop)")
    try:
        await asyncio.Event().wait()  # run until interrupted
    finally:
        await phone.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sip-server", required=True)
    parser.add_argument("--sip-port", type=int, default=5060)
    parser.add_argument("--sip-user", required=True)
    parser.add_argument("--sip-password", required=True)
    parser.add_argument("--my-ip", default="", help="Override auto-detected local IP")
    parser.add_argument("--local-sip-port", type=int, default=15060)
    parser.add_argument("--rtp-port-low", type=int, default=20000)
    parser.add_argument("--rtp-port-high", type=int, default=20010)
    parser.add_argument("--ws-url", required=True, help="e.g. ws://127.0.0.1:8000/ws/call")
    parser.add_argument("--script", required=True, help="Path to a call-script JSON file")
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument(
        "--pre-roll-s", type=float, default=3.0,
        help="Seconds to wait after answer before bridging (voip24h PSTN-bridge delay workaround)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
