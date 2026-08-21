"""SIP dialog routing: where the BYE that ends a call is actually sent.

Regression cover for a bug that only ever showed up against a peer other than
the registered trunk: `SipPhone.hangup()` addressed the BYE to the configured
server instead of the dialog's own peer, so when the AI hung up the caller
never learned about it and sat on an open, silent line.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from sip import messages as m
from sip.client import SipCall, SipPhone


def _phone() -> tuple[SipPhone, MagicMock]:
    phone = SipPhone(
        server="222.255.115.80",
        port=5060,
        username="642",
        password="secret",
        my_ip="192.168.1.3",
        sip_port=15060,
        rtp_port_low=20000,
        rtp_port_high=20010,
        on_call_start=lambda call: asyncio.sleep(0),
    )
    transport = MagicMock()
    phone._transport = transport
    return phone, transport


def _register_call(phone: SipPhone, remote_addr: tuple[str, int] | None) -> SipCall:
    rtp = MagicMock()
    rtp.close = MagicMock()
    call = SipCall(
        call_id="abc123",
        caller_number="faketest",
        rtp=rtp,
        local_from="<sip:642@222.255.115.80>;tag=local",
        remote_to="<sip:faketest@127.0.0.1>;tag=remote",
        remote_target="sip:faketest@127.0.0.1:15070",
        remote_addr=remote_addr,
    )
    phone._active_calls["abc123"] = call
    return call


@pytest.mark.asyncio
async def test_bye_goes_to_the_dialog_peer_not_the_registered_trunk():
    phone, transport = _phone()
    _register_call(phone, ("127.0.0.1", 15070))

    await phone.hangup("abc123")

    (data, addr), _ = transport.sendto.call_args
    assert addr == ("127.0.0.1", 15070)
    assert m.parse(data).method == "BYE"


@pytest.mark.asyncio
async def test_bye_falls_back_to_the_trunk_when_the_peer_address_is_unknown():
    """An older call object (or one restored without transport info) must still
    produce a BYE rather than crashing the teardown."""
    phone, transport = _phone()
    _register_call(phone, None)

    await phone.hangup("abc123")

    (_, addr), _ = transport.sendto.call_args
    assert addr == ("222.255.115.80", 5060)


@pytest.mark.asyncio
async def test_hangup_is_a_noop_for_an_unknown_call():
    phone, transport = _phone()

    await phone.hangup("not-a-call")

    transport.sendto.assert_not_called()
