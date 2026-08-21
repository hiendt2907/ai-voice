"""Minimal SIP UA — registers as an extension, answers one INVITE at a
time. Built to replace the FreeSWITCH + mod_audio_fork path (see
sip/messages.py's module docstring for why) with a small, fully-owned
asyncio component instead of a third-party C module we can't fix.

Not a general-purpose softphone: single registration, one call in
flight, G.711 only, no re-INVITE/hold/transfer. That's all voip24h's
click-to-call flow (ring extension → bridge to a phone number) needs.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sip import messages as m
from sip import sdp
from sip.rtp_session import RtpSession

logger = logging.getLogger(__name__)

_REGISTER_RETRY_S = 30
_DEFAULT_EXPIRES = 600


@dataclass
class SipCall:
    call_id: str
    caller_number: str
    rtp: RtpSession
    # Dialog identifiers captured from the INVITE / our 200 OK, needed to
    # send a well-formed BYE when *we* end the call (UAS role: our tag is in
    # From, theirs in To — the mirror image of the INVITE).
    local_from: str = ""
    remote_to: str = ""
    remote_target: str = ""
    # Transport address the INVITE actually came from. The BYE that ends the
    # call has to go back *there*, not to the registered trunk — see
    # SipPhone.hangup().
    remote_addr: tuple[str, int] | None = None
    cseq: int = 0

    def flush_playback(self) -> None:
        self.rtp.flush_playback()


class _SipProtocol(asyncio.DatagramProtocol):
    def __init__(self, phone: SipPhone) -> None:
        self._phone = phone

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._phone._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            msg = m.parse(data)
        except ValueError as exc:
            logger.warning("Dropping unparseable SIP datagram: %s", exc)
            return
        self._phone._handle_message(msg, addr)

    def error_received(self, exc: Exception) -> None:
        logger.warning("SIP socket error: %s", exc)


class SipPhone:
    def __init__(
        self,
        *,
        server: str,
        port: int,
        username: str,
        password: str,
        my_ip: str,
        sip_port: int,
        rtp_port_low: int,
        rtp_port_high: int,
        on_call_start: Callable[[SipCall], Awaitable[None]],
        on_call_end: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.my_ip = my_ip
        self.sip_port = sip_port
        self._rtp_ports = list(range(rtp_port_low, rtp_port_high + 1, 2))
        self._on_call_start = on_call_start
        self._on_call_end = on_call_end

        self._transport: asyncio.DatagramTransport | None = None
        self._register_call_id = m.new_call_id()
        self._register_cseq = 0
        self._register_task: asyncio.Task | None = None
        self._active_calls: dict[str, SipCall] = {}
        self._active_rtp_ports: set[int] = set()

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _SipProtocol(self), local_addr=("0.0.0.0", self.sip_port)  # noqa: S104
        )
        self._register_task = asyncio.create_task(self._register_loop())

    async def stop(self) -> None:
        if self._register_task:
            self._register_task.cancel()
        for call in list(self._active_calls.values()):
            call.rtp.close()
        if self._transport:
            self._transport.close()

    def _send(self, data: bytes) -> None:
        """For requests *we* originate against our configured peer (REGISTER)
        — always the registered server, correct by definition. In-dialog
        requests such as BYE do NOT belong here; they are addressed to the
        dialog's own peer via `_send_to`."""
        assert self._transport is not None
        self._transport.sendto(data, (self.server, self.port))

    def _send_to(self, data: bytes, addr: tuple[str, int]) -> None:
        """For responses to a request someone sent us (200 OK to their
        OPTIONS/INVITE/BYE). RFC 3261 routes a response back via the request's
        actual source, not a fixed configured peer — `_send()` did this for
        every response until now, which happened to work for voip24h (its
        signaling source has been stable) but silently breaks the moment a
        request arrives from anywhere else, including any SBC hop that
        doesn't source from the exact registered address:port."""
        assert self._transport is not None
        self._transport.sendto(data, addr)

    async def _register_loop(self) -> None:
        while True:
            try:
                await self._register_once()
            except Exception as exc:
                logger.warning("REGISTER failed: %s", exc)
            await asyncio.sleep(_REGISTER_RETRY_S)

    async def _register_once(self) -> None:
        self._register_cseq += 1
        branch = m.new_branch()
        tag = m.new_tag()
        req = m.build_register(
            server=self.server,
            port=self.port,
            username=self.username,
            my_ip=self.my_ip,
            my_port=self.sip_port,
            call_id=self._register_call_id,
            cseq=self._register_cseq,
            branch=branch,
            tag=tag,
        )
        self._pending_register = asyncio.get_running_loop().create_future()
        self._send(req)
        try:
            resp = await asyncio.wait_for(self._pending_register, timeout=5)
        except TimeoutError:
            raise RuntimeError("REGISTER timed out (no response)") from None

        if resp.status_code in (401, 407):
            www_auth = resp.header("www-authenticate") or resp.header("proxy-authenticate")
            if not www_auth:
                raise RuntimeError(f"REGISTER challenged ({resp.status_code}) but no auth header")
            params = m.parse_www_authenticate(www_auth)
            auth_header = "Authorization: " + m.build_digest_auth(
                username=self.username,
                password=self.password,
                realm=params.get("realm", ""),
                nonce=params.get("nonce", ""),
                method="REGISTER",
                uri=f"sip:{self.server}",
                qop=params.get("qop"),
            )
            self._register_cseq += 1
            req = m.build_register(
                server=self.server,
                port=self.port,
                username=self.username,
                my_ip=self.my_ip,
                my_port=self.sip_port,
                call_id=self._register_call_id,
                cseq=self._register_cseq,
                branch=m.new_branch(),
                tag=tag,
                auth_header=auth_header.split(": ", 1)[1],
            )
            self._pending_register = asyncio.get_running_loop().create_future()
            self._send(req)
            resp = await asyncio.wait_for(self._pending_register, timeout=5)

        if resp.status_code == 200:
            logger.info("SIP REGISTER OK (%s@%s)", self.username, self.server)
        else:
            raise RuntimeError(f"REGISTER rejected: {resp.status_code} {resp.reason}")

    def _handle_message(self, msg: m.SipMessage, addr: tuple[str, int]) -> None:
        if msg.status_code is not None:
            self._handle_response(msg)
        else:
            asyncio.create_task(self._handle_request(msg, addr))

    def _handle_response(self, msg: m.SipMessage) -> None:
        if msg.cseq_method == "REGISTER":
            fut = getattr(self, "_pending_register", None)
            if fut and not fut.done():
                fut.set_result(msg)

    async def _handle_request(self, req: m.SipMessage, addr: tuple[str, int]) -> None:
        if req.method == "OPTIONS":
            self._send_to(m.build_response(req, 200, "OK", my_ip=self.my_ip, my_port=self.sip_port), addr)
        elif req.method == "INVITE":
            await self._handle_invite(req, addr)
        elif req.method == "ACK":
            pass  # nothing to do — RTP session already started on our 200 OK
        elif req.method == "BYE":
            self._send_to(m.build_response(req, 200, "OK", my_ip=self.my_ip, my_port=self.sip_port), addr)
            await self._end_call(req.call_id)
        else:
            logger.debug("Unhandled SIP method: %s", req.method)

    def _allocate_rtp_port(self) -> int:
        for p in self._rtp_ports:
            if p not in self._active_rtp_ports:
                self._active_rtp_ports.add(p)
                return p
        raise RuntimeError("no free RTP ports")

    async def _handle_invite(self, req: m.SipMessage, addr: tuple[str, int]) -> None:
        try:
            offer = sdp.parse_offer(req.body)
        except ValueError as exc:
            logger.error("Bad SDP in INVITE, rejecting: %s", exc)
            self._send_to(
                m.build_response(req, 488, "Not Acceptable Here", my_ip=self.my_ip, my_port=self.sip_port), addr
            )
            return

        logger.debug(
            "SDP offer parsed: remote=%s:%d payload_types=%s",
            offer.connection_ip, offer.port, offer.payload_types,
        )
        payload_type = sdp.PT_PCMU if sdp.PT_PCMU in offer.payload_types else sdp.PT_PCMA
        local_tag = m.new_tag()
        rtp_port = self._allocate_rtp_port()

        answer_sdp = sdp.build_answer(
            my_ip=self.my_ip, rtp_port=rtp_port, payload_type=payload_type, session_id=req.call_id[:10]
        )
        self._send_to(
            m.build_response(
                req, 200, "OK",
                my_ip=self.my_ip, my_port=self.sip_port,
                local_tag=local_tag,
                body=answer_sdp, content_type="application/sdp",
            ),
            addr,
        )

        rtp = RtpSession(local_port=rtp_port, remote_ip=offer.connection_ip, remote_port=offer.port)
        await rtp.start()

        from_header = req.header("from") or ""
        caller_number = ""
        if 'sip:' in (req.header("from") or ""):
            with contextlib.suppress(IndexError):
                caller_number = from_header.split("sip:")[1].split("@")[0]

        to_header = req.header("to") or ""
        if "tag=" not in to_header:
            to_header = f"{to_header};tag={local_tag}"
        contact = req.header("contact") or ""
        remote_target = ""
        if "<" in contact and ">" in contact:
            remote_target = contact.split("<", 1)[1].split(">", 1)[0]
        elif contact:
            remote_target = contact.strip()
        if not remote_target and "sip:" in from_header:
            remote_target = "sip:" + from_header.split("sip:", 1)[1].split(">")[0].split(";")[0]

        call = SipCall(
            call_id=req.call_id,
            caller_number=caller_number,
            rtp=rtp,
            local_from=to_header,
            remote_to=req.header("from") or "",
            remote_target=remote_target,
            remote_addr=addr,
        )
        self._active_calls[req.call_id] = call
        logger.info("Call answered: call_id=%s caller=%s rtp_port=%d", req.call_id, caller_number, rtp_port)
        try:
            await self._on_call_start(call)
        finally:
            # The bridge returning means the AI side is done with this call
            # (hangup/handoff, or the WS dropped). Nothing used to hang up
            # the SIP leg in that case, so the caller sat on an open, silent
            # line until the carrier timed the call out.
            await self.hangup(req.call_id)

    async def hangup(self, call_id: str) -> None:
        """End a call we're still in by sending BYE, then tear it down.

        No-op if the call is already gone (the common case when the *caller*
        hung up first — we got their BYE and cleaned up in `_end_call`).
        """
        call = self._active_calls.get(call_id)
        if call is None:
            return
        call.cseq += 1
        try:
            # In-dialog request: it belongs to *this* call, so it goes to the
            # address the INVITE arrived from — the same RFC 3261 rule that
            # already applies to responses (`_send_to`). Sending it to the
            # configured trunk instead only works while the caller happens to
            # reach us through that exact address:port; for any other peer the
            # BYE lands nowhere, the caller never learns the AI hung up, and
            # the line stays open and silent until the carrier times it out.
            self._send_to(
                m.build_bye(
                    call_id=call_id,
                    from_header=call.local_from,
                    to_header=call.remote_to,
                    request_uri=call.remote_target,
                    my_ip=self.my_ip,
                    my_port=self.sip_port,
                    cseq=call.cseq,
                ),
                call.remote_addr or (self.server, self.port),
            )
            logger.info("Sent BYE for call_id=%s", call_id)
        except Exception as exc:  # noqa: BLE001 — teardown must still run
            logger.warning("Failed to send BYE for call_id=%s: %s", call_id, exc)
        await self._end_call(call_id)

    async def _end_call(self, call_id: str) -> None:
        call = self._active_calls.pop(call_id, None)
        if call is None:
            return
        self._active_rtp_ports.discard(call.rtp.local_port)
        call.rtp.close()
        if self._on_call_end:
            await self._on_call_end(call_id)
        logger.info("Call ended: call_id=%s", call_id)
