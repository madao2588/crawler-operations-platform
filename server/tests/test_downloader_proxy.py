from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

import app.engine.downloader as downloader
from app.utils.url_security import UnsafeTargetError


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "outbound_proxy_url": None,
        "use_system_proxy": True,
        "outbound_no_proxy": "localhost,127.0.0.1,::1",
        "timeout": 30,
        "max_retry": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_resolve_outbound_proxy_prefers_explicit_task_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(downloader, "settings", _settings())

    resolved = downloader.resolve_outbound_proxy(
        "https://example.com/notices",
        {"server": "http://task-proxy.example:8080", "username": "u", "password": "p"},
        system_proxies={"https": "http://system-proxy.example:7890"},
    )

    assert resolved == {
        "server": "http://task-proxy.example:8080",
        "username": "u",
        "password": "p",
    }


def test_explicit_task_proxy_overrides_configured_no_proxy_for_remote_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        downloader,
        "settings",
        _settings(outbound_no_proxy="localhost,127.0.0.1,service.most.gov.cn"),
    )

    resolved = downloader.resolve_outbound_proxy(
        "https://service.most.gov.cn/kjjh_tztg/",
        {"server": "http://working-proxy.example:8080"},
    )

    assert resolved == {"server": "http://working-proxy.example:8080"}


def test_resolve_outbound_proxy_uses_configured_proxy_before_windows_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        downloader,
        "settings",
        _settings(outbound_proxy_url="127.0.0.1:7897"),
    )

    resolved = downloader.resolve_outbound_proxy(
        "https://service.most.gov.cn/kjjh_tztg/",
        system_proxies={"https": "http://system-proxy.example:7890"},
    )

    assert resolved == {"server": "http://127.0.0.1:7897"}


def test_resolve_outbound_proxy_reads_system_proxy_for_url_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(downloader, "settings", _settings())

    resolved = downloader.resolve_outbound_proxy(
        "https://service.most.gov.cn/kjjh_tztg/",
        system_proxies={
            "http": "http://127.0.0.1:8080",
            "https": "http://127.0.0.1:7897",
        },
    )

    assert resolved == {"server": "http://127.0.0.1:7897"}


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/health",
        "http://localhost:8093/",
        "http://[::1]:8000/health",
    ],
)
def test_resolve_outbound_proxy_never_proxies_local_services(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
) -> None:
    monkeypatch.setattr(
        downloader,
        "settings",
        _settings(outbound_proxy_url="http://127.0.0.1:7897"),
    )

    assert downloader.resolve_outbound_proxy(url) is None


@pytest.mark.asyncio
async def test_fetch_static_passes_resolved_proxy_to_httpx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(
            self,
            _url: str,
            *,
            cookies: object = None,
        ) -> FakeResponse:
            _ = cookies
            return FakeResponse()

    monkeypatch.setattr(downloader, "settings", _settings())
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    html = await downloader.fetch_static(
        "https://example.com/notices",
        proxy={"server": "http://127.0.0.1:7897"},
    )

    assert html == "<html>ok</html>"
    assert captured["proxy"] == "http://127.0.0.1:7897"


@pytest.mark.asyncio
async def test_fetch_static_automatically_falls_back_to_direct_when_global_proxy_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_proxies: list[object] = []

    class FakeResponse:
        text = "<html>direct ok</html>"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.proxy = kwargs.get("proxy")
            attempted_proxies.append(self.proxy)

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, url: str, *, cookies: object = None) -> FakeResponse:
            _ = cookies
            if self.proxy is not None:
                raise httpx.ConnectError(
                    "proxy connection failed",
                    request=httpx.Request("GET", url),
                )
            return FakeResponse()

    monkeypatch.setattr(
        downloader,
        "settings",
        _settings(
            outbound_proxy_url="http://host.docker.internal:7897",
            max_retry=2,
        ),
    )
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    html = await downloader.fetch_static("https://example.com/notices")

    assert html == "<html>direct ok</html>"
    assert attempted_proxies == ["http://host.docker.internal:7897", None]


@pytest.mark.asyncio
async def test_fetch_static_rejects_private_redirect_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        text = "<html>ok</html>"
        history = [object()]
        url = "http://169.254.169.254/latest/meta-data"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def get(self, _url: str, *, cookies: object = None) -> FakeResponse:
            _ = cookies
            return FakeResponse()

    monkeypatch.setattr(downloader, "settings", _settings())
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        downloader,
        "assert_safe_outbound_url",
        lambda url: url if "example.com" in url else (_ for _ in ()).throw(UnsafeTargetError("blocked")),
    )

    with pytest.raises(UnsafeTargetError, match="blocked"):
        await downloader.fetch_static("https://example.com/notices")
