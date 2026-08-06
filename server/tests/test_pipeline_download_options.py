import pytest

import app.engine.pipeline as pipeline_mod


class _FakeLogRepo:
    async def create(self, **kwargs) -> None:
        _ = kwargs


@pytest.mark.asyncio
async def test_download_page_passes_login_flow_to_dynamic(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_fetch_static(url: str, **kwargs) -> str:
        _ = (url, kwargs)
        raise RuntimeError("force dynamic fallback")

    async def fake_fetch_dynamic(url: str, **kwargs) -> str:
        captured["url"] = url
        captured.update(kwargs)
        return "<html>ok</html>"

    monkeypatch.setattr(pipeline_mod, "fetch_static", fake_fetch_static)
    monkeypatch.setattr(pipeline_mod, "fetch_dynamic", fake_fetch_dynamic)

    rules = {
        "http_headers": {"Accept-Language": "zh-CN"},
        "http_cookies": {"sid": "abc"},
        "cookie_domain": ".example.com",
        "dynamic_wait_selector": ".items a[href], .article-content",
        "login_username": "alice",
        "login_password": "secret",
        "login_flow": {
            "url": "https://example.com/login",
            "steps": [
                {"action": "fill", "selector": "#u", "value_from": "login_username"},
                {"action": "fill", "selector": "#p", "value_from": "login_password"},
                {"action": "click", "selector": "button"},
            ],
        },
    }

    html = await pipeline_mod._download_page(
        run_id="r1",
        task_id=1,
        log_repo=_FakeLogRepo(),
        url="https://example.com/protected",
        crawl_rules=rules,
    )

    assert html == "<html>ok</html>"
    assert captured["url"] == "https://example.com/protected"
    assert captured["cookie_domain"] == ".example.com"
    assert captured["wait_for_selector"] == ".items a[href], .article-content"
    assert isinstance(captured.get("cookies"), dict)
    login_flow = captured.get("login_flow")
    assert isinstance(login_flow, dict)
    assert login_flow["url"] == "https://example.com/login"
    assert login_flow["session_key"] == "task:1"
    assert login_flow["session_ttl_sec"] == 1800
    assert captured.get("proxy") is None


@pytest.mark.asyncio
async def test_download_page_raises_on_dynamic_anti_bot_when_retry_enabled(
    monkeypatch,
) -> None:
    async def fake_fetch_static(url: str, **kwargs) -> str:
        _ = (url, kwargs)
        raise RuntimeError("force dynamic")

    async def fake_fetch_dynamic(url: str, **kwargs) -> str:
        _ = (url, kwargs)
        return "<html>verify you are human</html>"

    monkeypatch.setattr(pipeline_mod, "fetch_static", fake_fetch_static)
    monkeypatch.setattr(pipeline_mod, "fetch_dynamic", fake_fetch_dynamic)

    rules = {
        "anti_bot_retry_on_block": True,
        "anti_bot_challenge_keywords": ["verify you are human"],
    }

    with pytest.raises(pipeline_mod.AntiBotBlockedError):
        await pipeline_mod._download_page(
            run_id="r2",
            task_id=1,
            log_repo=_FakeLogRepo(),
            url="https://example.com/protected",
            crawl_rules=rules,
        )


@pytest.mark.asyncio
async def test_download_page_returns_dynamic_html_when_retry_disabled(
    monkeypatch,
) -> None:
    async def fake_fetch_static(url: str, **kwargs) -> str:
        _ = (url, kwargs)
        raise RuntimeError("force dynamic")

    async def fake_fetch_dynamic(url: str, **kwargs) -> str:
        _ = (url, kwargs)
        return "<html>verify you are human</html>"

    monkeypatch.setattr(pipeline_mod, "fetch_static", fake_fetch_static)
    monkeypatch.setattr(pipeline_mod, "fetch_dynamic", fake_fetch_dynamic)

    rules = {
        "anti_bot_retry_on_block": False,
        "anti_bot_challenge_keywords": ["verify you are human"],
    }

    html = await pipeline_mod._download_page(
        run_id="r3",
        task_id=1,
        log_repo=_FakeLogRepo(),
        url="https://example.com/protected",
        crawl_rules=rules,
    )
    assert "verify you are human" in html


@pytest.mark.asyncio
async def test_download_page_failover_to_proxy_on_challenge(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def fake_fetch_static(url: str, **kwargs) -> str:
        _ = (url, kwargs)
        raise RuntimeError("force dynamic")

    async def fake_fetch_dynamic(url: str, **kwargs) -> str:
        _ = url
        calls.append(kwargs)
        proxy = kwargs.get("proxy")
        if proxy is None:
            return "<html>verify you are human</html>"
        return "<html>ok</html>"

    monkeypatch.setattr(pipeline_mod, "fetch_static", fake_fetch_static)
    monkeypatch.setattr(pipeline_mod, "fetch_dynamic", fake_fetch_dynamic)

    rules = {
        "anti_bot_retry_on_block": True,
        "anti_bot_challenge_keywords": ["verify you are human"],
        "proxy_server": "http://127.0.0.1:8080",
        "proxy_on_block_only": True,
        "proxy_failover_enabled": True,
    }

    html = await pipeline_mod._download_page(
        run_id="r4",
        task_id=1,
        log_repo=_FakeLogRepo(),
        url="https://example.com/protected",
        crawl_rules=rules,
    )

    assert html == "<html>ok</html>"
    assert len(calls) == 2
    assert calls[0].get("proxy") is None
    assert isinstance(calls[1].get("proxy"), dict)
