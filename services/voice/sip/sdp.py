"""Minimal SDP — just enough to read the caller's offered RTP port/codecs
and build our own answer. No video, no ICE, no multiple m-lines."""

from __future__ import annotations

from dataclasses import dataclass

# RTP payload type numbers for the two codecs we actually support (RFC 3551
# static assignments — these numbers are standardized, not negotiated).
PT_PCMU = 0
PT_PCMA = 8


@dataclass
class RemoteAudioOffer:
    connection_ip: str
    port: int
    payload_types: list[int]


def parse_offer(body: str) -> RemoteAudioOffer:
    conn_ip = ""
    port = 0
    payload_types: list[int] = []

    for line in body.splitlines():
        line = line.strip()
        if line.startswith("c="):
            # c=IN IP4 1.2.3.4
            parts = line.split()
            if len(parts) >= 3:
                conn_ip = parts[2]
        elif line.startswith("m=audio"):
            # m=audio 17796 RTP/AVP 0 101
            parts = line.split()
            if len(parts) >= 2:
                port = int(parts[1])
            payload_types = [int(p) for p in parts[3:] if p.isdigit()]

    if not conn_ip or not port:
        raise ValueError(f"could not parse SDP audio offer: {body!r}")
    return RemoteAudioOffer(connection_ip=conn_ip, port=port, payload_types=payload_types)


def build_answer(*, my_ip: str, rtp_port: int, payload_type: int, session_id: str) -> str:
    codec_name = "PCMU" if payload_type == PT_PCMU else "PCMA"
    lines = [
        "v=0",
        f"o=ai-voice {session_id} {session_id} IN IP4 {my_ip}",
        "s=ai-voice",
        f"c=IN IP4 {my_ip}",
        "t=0 0",
        f"m=audio {rtp_port} RTP/AVP {payload_type}",
        f"a=rtpmap:{payload_type} {codec_name}/8000",
        "a=ptime:20",
        "a=sendrecv",
    ]
    return "\r\n".join(lines) + "\r\n"
