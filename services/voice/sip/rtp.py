"""RTP packet framing (RFC 3550) — just the fixed 12-byte header, no
extensions/CSRC. G.711 (PCMU/PCMA) payload only, 20ms/160-byte frames."""

from __future__ import annotations

import random
import struct
from dataclasses import dataclass

_HEADER = struct.Struct("!BBHII")  # version/flags, marker+PT, seq, timestamp, ssrc
_RTP_VERSION = 2
_CLOCK_RATE = 8000
_SAMPLES_PER_FRAME = 160  # 20ms @ 8kHz


@dataclass
class RtpPacket:
    payload_type: int
    sequence: int
    timestamp: int
    ssrc: int
    marker: bool
    payload: bytes


def parse(data: bytes) -> RtpPacket | None:
    if len(data) < 12:
        return None
    b0, b1, seq, ts, ssrc = _HEADER.unpack_from(data, 0)
    version = b0 >> 6
    if version != _RTP_VERSION:
        return None
    cc = b0 & 0x0F
    offset = 12 + cc * 4
    if b0 & 0x10:  # extension header present
        if len(data) < offset + 4:
            return None
        ext_len_words = struct.unpack_from("!H", data, offset + 2)[0]
        offset += 4 + ext_len_words * 4
    marker = bool(b1 & 0x80)
    payload_type = b1 & 0x7F
    return RtpPacket(
        payload_type=payload_type,
        sequence=seq,
        timestamp=ts,
        ssrc=ssrc,
        marker=marker,
        payload=data[offset:],
    )


def build(*, payload_type: int, sequence: int, timestamp: int, ssrc: int, payload: bytes, marker: bool = False) -> bytes:
    b0 = (_RTP_VERSION << 6)
    b1 = (0x80 if marker else 0x00) | (payload_type & 0x7F)
    header = _HEADER.pack(b0, b1, sequence & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc)
    return header + payload


def new_ssrc() -> int:
    return random.randint(1, 0xFFFFFFFF)


class SequenceCounter:
    """Wrapping 16-bit sequence + 32-bit timestamp counters for one outbound
    RTP stream, starting from random values per RFC 3550 §5.1."""

    def __init__(self) -> None:
        self.sequence = random.randint(0, 0xFFFF)
        self.timestamp = random.randint(0, 0xFFFFFFFF)

    def next(self) -> tuple[int, int]:
        seq, ts = self.sequence, self.timestamp
        self.sequence = (self.sequence + 1) & 0xFFFF
        self.timestamp = (self.timestamp + _SAMPLES_PER_FRAME) & 0xFFFFFFFF
        return seq, ts
