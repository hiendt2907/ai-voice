"""Minimal SIP message parsing/building — just enough to REGISTER as a UA
and answer an incoming INVITE (voip24h's /v3/call/dial rings us like a real
extension; see services/voice/sip/README.md for the call flow this exists
to replace — mod_audio_fork's write-replace media bug path never actually
delivered audio to the RTP stream, confirmed via direct FreeSWITCH-core
instrumentation, so this package talks SIP/RTP directly instead).

Deliberately not a general-purpose SIP stack: no proxies, no multiple
simultaneous calls, no re-INVITE, no video. Just REGISTER (with digest
auth) + receive one INVITE at a time + ACK/BYE/OPTIONS.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

_SIP_VERSION = "SIP/2.0"
USER_AGENT = "ai-voice-sip/0.1"


def new_tag() -> str:
    return uuid.uuid4().hex[:10]


def new_call_id() -> str:
    return uuid.uuid4().hex


def new_branch() -> str:
    # RFC 3261 magic cookie prefix, required for RFC3261-compliant loop detection.
    return "z9hG4bK" + uuid.uuid4().hex[:16]


@dataclass
class SipMessage:
    """A parsed SIP message — either a request (method+uri set) or a
    response (status_code+reason set)."""

    method: str | None = None
    uri: str | None = None
    status_code: int | None = None
    reason: str | None = None
    headers: dict[str, list[str]] = field(default_factory=dict)
    body: str = ""

    def header(self, name: str) -> str | None:
        vals = self.headers.get(name.lower())
        return vals[0] if vals else None

    def headers_all(self, name: str) -> list[str]:
        return self.headers.get(name.lower(), [])

    @property
    def call_id(self) -> str:
        return self.header("call-id") or ""

    @property
    def cseq_num(self) -> int:
        cseq = self.header("cseq") or "0"
        return int(cseq.split()[0])

    @property
    def cseq_method(self) -> str:
        cseq = self.header("cseq") or ""
        parts = cseq.split()
        return parts[1] if len(parts) > 1 else ""


_STATUS_LINE_RE = re.compile(r"^SIP/2\.0\s+(\d{3})\s+(.*)$")
_REQUEST_LINE_RE = re.compile(r"^(\w+)\s+(\S+)\s+SIP/2\.0$")


def parse(raw: bytes) -> SipMessage:
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\r\n")
    if not lines:
        raise ValueError("empty SIP message")

    msg = SipMessage()
    first = lines[0]
    m = _STATUS_LINE_RE.match(first)
    if m:
        msg.status_code = int(m.group(1))
        msg.reason = m.group(2)
    else:
        m = _REQUEST_LINE_RE.match(first)
        if not m:
            raise ValueError(f"unparseable SIP start line: {first!r}")
        msg.method = m.group(1)
        msg.uri = m.group(2)

    i = 1
    while i < len(lines) and lines[i] != "":
        line = lines[i]
        if ":" in line:
            name, _, value = line.partition(":")
            key = name.strip().lower()
            msg.headers.setdefault(key, []).append(value.strip())
        i += 1

    msg.body = "\r\n".join(lines[i + 1 :]) if i + 1 < len(lines) else ""
    return msg


def _serialize_headers(headers: list[tuple[str, str]]) -> str:
    return "".join(f"{name}: {value}\r\n" for name, value in headers)


def build_register(
    *,
    server: str,
    port: int,
    username: str,
    my_ip: str,
    my_port: int,
    call_id: str,
    cseq: int,
    branch: str,
    tag: str,
    expires: int = 600,
    auth_header: str | None = None,
) -> bytes:
    uri = f"sip:{server}"
    headers = [
        ("Via", f"SIP/2.0/UDP {my_ip}:{my_port};branch={branch};rport"),
        ("Max-Forwards", "70"),
        ("From", f'<sip:{username}@{server}>;tag={tag}'),
        ("To", f"<sip:{username}@{server}>"),
        ("Call-ID", call_id),
        ("CSeq", f"{cseq} REGISTER"),
        ("Contact", f"<sip:{username}@{my_ip}:{my_port}>"),
        ("Expires", str(expires)),
        ("User-Agent", USER_AGENT),
        ("Content-Length", "0"),
    ]
    if auth_header:
        headers.insert(-1, ("Authorization", auth_header))
    msg = f"REGISTER {uri} SIP/2.0\r\n" + _serialize_headers(headers) + "\r\n"
    return msg.encode("utf-8")


def build_invite(
    *,
    target_uri: str,
    server: str,
    port: int,
    username: str,
    my_ip: str,
    my_port: int,
    call_id: str,
    cseq: int,
    branch: str,
    tag: str,
    sdp_body: str,
) -> bytes:
    """UAC-side INVITE — only used by the test tool (sip/fake_caller.py) that
    calls our own softphone directly to simulate voip24h without a real PSTN
    leg. The softphone itself is answer-only and never builds this."""
    body_bytes = sdp_body.encode("utf-8")
    headers = [
        ("Via", f"SIP/2.0/UDP {my_ip}:{my_port};branch={branch};rport"),
        ("Max-Forwards", "70"),
        ("From", f'<sip:{username}@{my_ip}>;tag={tag}'),
        ("To", f"<{target_uri}>"),
        ("Call-ID", call_id),
        ("CSeq", f"{cseq} INVITE"),
        ("Contact", f"<sip:{username}@{my_ip}:{my_port}>"),
        ("User-Agent", USER_AGENT),
        ("Content-Type", "application/sdp"),
        ("Content-Length", str(len(body_bytes))),
    ]
    msg = f"INVITE {target_uri} SIP/2.0\r\n" + _serialize_headers(headers) + "\r\n" + sdp_body
    return msg.encode("utf-8")


def build_digest_auth(
    *,
    username: str,
    password: str,
    realm: str,
    nonce: str,
    method: str,
    uri: str,
    qop: str | None = None,
    nc: str = "00000001",
    cnonce: str | None = None,
    algorithm: str = "MD5",
    scheme_header: str = "Authorization",
) -> str:
    """RFC 2617 MD5 digest response. `scheme_header` is unused (kept for
    call-site clarity — Authorization vs Proxy-Authorization headers share
    this exact digest computation)."""
    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
    if qop:
        cnonce = cnonce or uuid.uuid4().hex[:8]
        response = hashlib.md5(
            f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
        ).hexdigest()
        return (
            f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{uri}", response="{response}", algorithm={algorithm}, '
            f'qop={qop}, nc={nc}, cnonce="{cnonce}"'
        )
    response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
    return (
        f'Digest username="{username}", realm="{realm}", nonce="{nonce}", '
        f'uri="{uri}", response="{response}", algorithm={algorithm}'
    )


def parse_www_authenticate(header_value: str) -> dict[str, str]:
    """Parse `Digest realm="...", nonce="...", qop="auth", ...` into a dict."""
    params: dict[str, str] = {}
    body = header_value.split(" ", 1)[1] if " " in header_value else header_value
    for part in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', body):
        key, quoted, bare = part
        params[key] = quoted or bare
    return params


def build_response(
    request: SipMessage,
    status_code: int,
    reason: str,
    *,
    my_ip: str,
    my_port: int,
    local_tag: str | None = None,
    extra_headers: list[tuple[str, str]] | None = None,
    body: str = "",
    content_type: str | None = None,
) -> bytes:
    to_header = request.header("to") or ""
    if local_tag and "tag=" not in to_header:
        to_header = f"{to_header};tag={local_tag}"

    headers = [
        ("Via", v) for v in request.headers_all("via")
    ] + [
        ("From", request.header("from") or ""),
        ("To", to_header),
        ("Call-ID", request.call_id),
        ("CSeq", request.header("cseq") or ""),
        ("User-Agent", USER_AGENT),
    ]
    if request.method == "INVITE" and status_code == 200:
        headers.append(("Contact", f"<sip:{request.uri}>" if request.uri else f"<sip:{my_ip}:{my_port}>"))
    if extra_headers:
        headers.extend(extra_headers)
    if content_type and body:
        headers.append(("Content-Type", content_type))
        headers.append(("Content-Length", str(len(body.encode()))))
    else:
        headers.append(("Content-Length", str(len(body.encode()))))

    msg = (
        f"SIP/2.0 {status_code} {reason}\r\n"
        + _serialize_headers(headers)
        + "\r\n"
        + body
    )
    return msg.encode("utf-8")


def build_ack(request: SipMessage, *, my_ip: str, my_port: int, branch: str) -> bytes:
    headers = [
        ("Via", f"SIP/2.0/UDP {my_ip}:{my_port};branch={branch};rport"),
        ("Max-Forwards", "70"),
        ("From", request.header("from") or ""),
        ("To", request.header("to") or ""),
        ("Call-ID", request.call_id),
        ("CSeq", f"{request.cseq_num} ACK"),
        ("Content-Length", "0"),
    ]
    uri = request.uri or ""
    msg = f"ACK {uri} SIP/2.0\r\n" + _serialize_headers(headers) + "\r\n"
    return msg.encode("utf-8")


def build_bye(
    *,
    call_id: str,
    from_header: str,
    to_header: str,
    request_uri: str,
    my_ip: str,
    my_port: int,
    cseq: int,
) -> bytes:
    headers = [
        ("Via", f"SIP/2.0/UDP {my_ip}:{my_port};branch={new_branch()};rport"),
        ("Max-Forwards", "70"),
        ("From", from_header),
        ("To", to_header),
        ("Call-ID", call_id),
        ("CSeq", f"{cseq} BYE"),
        ("User-Agent", USER_AGENT),
        ("Content-Length", "0"),
    ]
    msg = f"BYE {request_uri} SIP/2.0\r\n" + _serialize_headers(headers) + "\r\n"
    return msg.encode("utf-8")
