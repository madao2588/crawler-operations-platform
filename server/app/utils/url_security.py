from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlparse


_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
    }
)

_BLOCKED_IP_STRINGS = frozenset(
    {
        "100.100.100.200",  # Alibaba Cloud metadata
        "100.100.100.201",
        "169.254.169.254",  # Common cloud metadata endpoint
    }
)

# Clash and similar split-tunnel clients commonly map public DNS names into the
# RFC 2544 benchmarking range, then route those synthetic addresses through a
# local proxy. It is neither loopback, RFC1918 nor a metadata range. Allowing it
# keeps public-host validation compatible with that network mode while all
# literal/private/link-local targets remain blocked.
_PROXY_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


class UnsafeTargetError(ValueError):
    """Raised when an outbound URL resolves to a non-public target."""


def validate_public_http_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeTargetError("URL must start with http:// or https://")

    host = _normalize_hostname(parsed.hostname)
    if host is None:
        raise UnsafeTargetError("URL must include a hostname")

    if host in _BLOCKED_HOSTNAMES:
        raise UnsafeTargetError(f"URL host {host} is not allowed")

    literal_ip = _parse_ip(host)
    if literal_ip is not None and _is_blocked_ip(literal_ip):
        raise UnsafeTargetError(f"URL host {host} is not a public address")

    return url.strip()


def assert_safe_outbound_url(
    url: str,
    *,
    resolver=None,
) -> str:
    normalized = validate_public_http_url(url)
    host = _normalize_hostname(urlparse(normalized).hostname)
    assert host is not None

    literal_ip = _parse_ip(host)
    if literal_ip is not None:
        return normalized

    resolved_ips = resolve_hostname_ips(host, resolver=resolver)
    if not resolved_ips:
        raise UnsafeTargetError(f"Could not resolve public address for host {host}")
    for address in resolved_ips:
        if _is_blocked_ip(address) and not _is_proxy_fake_ip(address):
            raise UnsafeTargetError(
                f"Resolved address {address.compressed} for host {host} is not public"
            )
    return normalized


def resolve_hostname_ips(
    hostname: str,
    *,
    resolver=None,
) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    normalized = _normalize_hostname(hostname)
    if normalized is None:
        raise UnsafeTargetError("Hostname is required")

    literal_ip = _parse_ip(normalized)
    if literal_ip is not None:
        return {literal_ip}

    hostname_resolver = resolver or socket.getaddrinfo
    try:
        records = hostname_resolver(normalized, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeTargetError(f"Could not resolve public address for host {normalized}") from exc

    addresses: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for record in records:
        sockaddr = record[4]
        if not isinstance(sockaddr, tuple) or not sockaddr:
            continue
        candidate = _parse_ip(str(sockaddr[0]))
        if candidate is not None:
            addresses.add(candidate)
    return addresses


def normalize_allowed_hosts(hosts: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for raw_host in hosts:
        host = _normalize_hostname(raw_host)
        if host is not None:
            normalized.add(host)
    return normalized


def _normalize_hostname(raw_host: str | None) -> str | None:
    if not isinstance(raw_host, str):
        return None
    host = raw_host.strip().lower().rstrip(".")
    return host or None


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_blocked_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.compressed.lower() in _BLOCKED_IP_STRINGS:
        return True
    return not address.is_global


def _is_proxy_fake_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return isinstance(address, ipaddress.IPv4Address) and address in _PROXY_FAKE_IP_NETWORK
