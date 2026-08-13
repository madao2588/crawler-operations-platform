from __future__ import annotations

import socket

import pytest

from app.utils.url_security import UnsafeTargetError, assert_safe_outbound_url, validate_public_http_url


@pytest.mark.parametrize(
    ("url", "needle"),
    [
        ("http://127.0.0.1:8000/health", "not a public address"),
        ("http://localhost:8093/", "not allowed"),
        ("http://169.254.169.254/latest/meta-data", "not a public address"),
        ("http://10.0.0.8/admin", "not a public address"),
        ("http://198.18.0.42/admin", "not a public address"),
        ("http://[::1]/", "not a public address"),
        ("file:///etc/passwd", "http:// or https://"),
    ],
)
def test_validate_public_http_url_rejects_local_and_non_http_targets(url: str, needle: str) -> None:
    with pytest.raises(UnsafeTargetError, match=needle):
        validate_public_http_url(url)


def test_assert_safe_outbound_url_rejects_dns_rebinding_to_private_ip() -> None:
    def fake_resolver(host: str, *_args, **_kwargs):
        assert host == "safe.example"
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.10", 443)),
        ]

    with pytest.raises(UnsafeTargetError, match="Resolved address 10.0.0.10"):
        assert_safe_outbound_url("https://safe.example/notices", resolver=fake_resolver)


def test_assert_safe_outbound_url_accepts_public_resolution() -> None:
    def fake_resolver(host: str, *_args, **_kwargs):
        assert host == "safe.example"
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0)),
        ]

    assert (
        assert_safe_outbound_url("https://safe.example/notices", resolver=fake_resolver)
        == "https://safe.example/notices"
    )


def test_assert_safe_outbound_url_accepts_proxy_fake_ip_resolution() -> None:
    def fake_resolver(_host: str, *_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.42", 443))]

    assert (
        assert_safe_outbound_url("https://public.example/notices", resolver=fake_resolver)
        == "https://public.example/notices"
    )
