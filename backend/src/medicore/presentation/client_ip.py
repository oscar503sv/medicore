"""Client IP resolution honoring X-Forwarded-For only from trusted proxies.

The header is attacker-controlled input: anyone can send it. It only becomes
meaningful when the directly-connected peer is a reverse proxy we operate, and even
then only the hops *that proxy* appended are reliable — anything the client put in
front of them is noise. Hence the right-to-left walk below.
"""

from __future__ import annotations

import ipaddress

from medicore.infrastructure.config import TrustedNetworks


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    value = value.strip()
    if value.startswith("["):  # [::1]:8080 → ::1
        value = value[1:].split("]")[0]
    elif value.count(":") == 1:  # 1.2.3.4:5678 → 1.2.3.4 (lone colon can't be IPv6)
        value = value.split(":")[0]
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_trusted(value: str, trusted: TrustedNetworks) -> bool:
    ip = _parse_ip(value)
    return ip is not None and any(ip in network for network in trusted)


def resolve_client_ip(
    peer: str | None, forwarded_for: str | None, trusted: TrustedNetworks
) -> str | None:
    """The real client IP for audit trails and session rows.

    - No trusted proxies configured, or the peer is not one of them → the header is
      untrusted input; the socket peer *is* the client.
    - Peer is a trusted proxy → walk X-Forwarded-For right to left skipping trusted
      hops; the first untrusted hop is the client. A malformed hop falls back to the
      peer, and a chain made entirely of trusted proxies yields its left-most hop.
    """
    if peer is None or not trusted or not _is_trusted(peer, trusted):
        return peer

    hops = [h.strip() for h in (forwarded_for or "").split(",") if h.strip()]
    if not hops:
        return peer

    leftmost: str | None = None
    for hop in reversed(hops):
        ip = _parse_ip(hop)
        if ip is None:
            return peer
        if not _is_trusted(hop, trusted):
            return str(ip)
        leftmost = str(ip)
    return leftmost
