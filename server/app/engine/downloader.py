import asyncio
import ipaddress
import time
from collections.abc import Mapping
from urllib.parse import urlparse
from urllib.request import getproxies

import httpx
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.core.config import get_settings
from app.utils.url_security import UnsafeTargetError, assert_safe_outbound_url


settings = get_settings()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

_LOGIN_STORAGE_CACHE: dict[str, tuple[float, dict[str, object]]] = {}
_LOGIN_STORAGE_CACHE_LOCK = asyncio.Lock()

_NETWORK_ERROR_MARKERS = (
    "connecterror",
    "networkerror",
    "connection closed",
    "connection reset",
    "err_connection_closed",
    "name or service not known",
    "nodename nor servname",
    "network is unreachable",
    "tls",
    "ssl",
    "handshake",
)


class FallbackFetchError(RuntimeError):
    def __init__(self, *, static_exc: BaseException, dynamic_exc: BaseException) -> None:
        self.static_exc = static_exc
        self.dynamic_exc = dynamic_exc
        super().__init__(
            "Static fetch failed before dynamic fallback also failed. "
            f"static={type(static_exc).__name__}: {static_exc}; "
            f"dynamic={type(dynamic_exc).__name__}: {dynamic_exc}"
        )


def classify_fetch_exception(exc: BaseException) -> str | None:
    for candidate in _walk_fetch_exceptions(exc):
        if isinstance(candidate, httpx.HTTPStatusError):
            status_code = candidate.response.status_code if candidate.response is not None else 0
            if status_code == 403:
                return "http_403"
            if status_code == 429:
                return "http_429"
            return "http_rejected"
        if isinstance(
            candidate,
            (httpx.TimeoutException, PlaywrightTimeoutError, TimeoutError, asyncio.TimeoutError),
        ):
            return "timeout"
        if isinstance(candidate, (httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError)):
            return "network_unreachable"

    text = " ".join(str(part).lower() for part in _collect_exception_text(exc))
    if any(marker in text for marker in _NETWORK_ERROR_MARKERS):
        return "network_unreachable"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "status code 403" in text or "403 forbidden" in text:
        return "http_403"
    if "status code 429" in text:
        return "http_429"
    if "httpstatuserror" in text or "err_http_response_code_failure" in text or "status code" in text:
        return "http_rejected"
    return None


def _walk_fetch_exceptions(exc: BaseException) -> list[BaseException]:
    seen: set[int] = set()
    queue: list[BaseException] = [exc]
    out: list[BaseException] = []
    while queue:
        current = queue.pop(0)
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(current)
        if isinstance(current, FallbackFetchError):
            queue.extend(
                item
                for item in (current.static_exc, current.dynamic_exc)
                if isinstance(item, BaseException)
            )
        if isinstance(current.__cause__, BaseException):
            queue.append(current.__cause__)
        if isinstance(current.__context__, BaseException):
            queue.append(current.__context__)
    return out


def _collect_exception_text(exc: BaseException) -> list[str]:
    parts: list[str] = []
    for candidate in _walk_fetch_exceptions(exc):
        parts.append(type(candidate).__name__)
        parts.append(str(candidate))
    return parts


async def fetch_static(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
    cookies: Mapping[str, str] | None = None,
    proxy: Mapping[str, object] | None = None,
) -> str:
    safe_url = assert_safe_outbound_url(url)
    timeout_sec = float(timeout) if timeout is not None else float(settings.timeout)
    merged: dict[str, str] = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)

    proxy_attempts = _outbound_proxy_attempts(safe_url, proxy)
    attempt_index = 0

    async def _request() -> str:
        nonlocal attempt_index
        client_timeout = httpx.Timeout(timeout_sec)
        client_kwargs: dict[str, object] = {
            "timeout": client_timeout,
            "follow_redirects": True,
            "headers": merged,
            "trust_env": False,
        }
        resolved_proxy = proxy_attempts[attempt_index % len(proxy_attempts)]
        attempt_index += 1
        httpx_proxy = _build_httpx_proxy(resolved_proxy)
        if httpx_proxy is not None:
            client_kwargs["proxy"] = httpx_proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.get(safe_url, cookies=cookies)
            response.raise_for_status()
            _assert_safe_httpx_response(response)
            return response.text

    return await _with_retry(_request)


async def _launch_chromium(chromium, launch_kwargs: dict[str, object]):
    try:
        return await chromium.launch(**launch_kwargs)
    except PlaywrightError as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        return await chromium.launch(**launch_kwargs, channel="chrome")


async def _wait_for_dynamic_content(
    page,
    *,
    wait_for_selector: str | None,
    timeout_ms: int,
) -> None:
    if wait_for_selector:
        await page.wait_for_selector(wait_for_selector, timeout=timeout_ms)
        await page.wait_for_timeout(250)
        return
    await page.wait_for_timeout(2000)


async def fetch_dynamic(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
    cookies: Mapping[str, str] | None = None,
    cookie_domain: str | None = None,
    login_flow: Mapping[str, object] | None = None,
    proxy: Mapping[str, object] | None = None,
    wait_for_selector: str | None = None,
) -> str:
    safe_url = assert_safe_outbound_url(url)
    timeout_sec = float(timeout) if timeout is not None else float(settings.timeout)
    timeout_ms = max(5_000, int(timeout_sec * 1000))

    merged: dict[str, str] = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    user_agent = merged.get("User-Agent") or DEFAULT_HEADERS["User-Agent"]
    extra_headers = {k: v for k, v in merged.items() if k.lower() != "user-agent"}

    proxy_attempts = _outbound_proxy_attempts(safe_url, proxy)
    attempt_index = 0

    async def _request() -> str:
        nonlocal attempt_index
        async with async_playwright() as playwright:
            launch_kwargs: dict[str, object] = {"headless": True}
            resolved_proxy = proxy_attempts[attempt_index % len(proxy_attempts)]
            attempt_index += 1
            browser_proxy = _build_playwright_proxy(
                resolved_proxy,
            )
            if browser_proxy is not None:
                launch_kwargs["proxy"] = browser_proxy
            browser = await _launch_chromium(playwright.chromium, launch_kwargs)
            try:
                cache_key, cache_ttl_sec = _resolve_session_cache_options(login_flow)
                cached_storage = await _get_cached_storage_state(cache_key)
                context_kwargs: dict[str, object] = {
                    "user_agent": user_agent,
                    "extra_http_headers": extra_headers or None,
                }
                if cached_storage is not None:
                    context_kwargs["storage_state"] = cached_storage
                context = await browser.new_context(**context_kwargs)
                await _attach_safe_route_guard(context)
                if cookies:
                    parsed = urlparse(safe_url)
                    if not parsed.scheme or not parsed.netloc:
                        raise ValueError("Invalid URL for cookie injection")
                    dom = (cookie_domain or "").strip()
                    if dom:
                        cookie_list = [{"name": n, "value": v, "domain": dom, "path": "/"} for n, v in cookies.items()]
                    else:
                        origin = f"{parsed.scheme}://{parsed.netloc}"
                        cookie_list = [{"name": n, "value": v, "url": origin, "path": "/"} for n, v in cookies.items()]
                    await context.add_cookies(cookie_list)
                page = await context.new_page()
                try:
                    if login_flow:
                        need_login = True
                        if cached_storage is not None:
                            need_login = not await _is_cached_login_session_valid(
                                page=page,
                                target_url=safe_url,
                                login_flow=login_flow,
                                default_timeout_ms=timeout_ms,
                            )
                        if need_login:
                            await _run_login_flow(
                                page=page,
                                target_url=safe_url,
                                login_flow=login_flow,
                                default_timeout_ms=timeout_ms,
                            )
                            if cache_key:
                                storage_state = await context.storage_state()
                                if isinstance(storage_state, dict):
                                    await _set_cached_storage_state(
                                        cache_key=cache_key,
                                        state=storage_state,
                                        ttl_sec=cache_ttl_sec,
                                    )
                    await page.goto(
                        safe_url,
                        timeout=timeout_ms,
                        wait_until="domcontentloaded",
                    )
                    _assert_safe_playwright_page(page)
                    await _wait_for_dynamic_content(
                        page,
                        wait_for_selector=wait_for_selector,
                        timeout_ms=timeout_ms,
                    )
                    return await page.content()
                finally:
                    await page.close()
                    await context.close()
            finally:
                await browser.close()

    return await _with_retry(_request)


def _outbound_proxy_attempts(
    url: str,
    explicit_proxy: Mapping[str, object] | None,
) -> tuple[dict[str, str] | None, ...]:
    resolved = resolve_outbound_proxy(url, explicit_proxy)
    if resolved is None or _normalize_proxy(explicit_proxy) is not None:
        return (resolved,)
    return (resolved, None)


def resolve_outbound_proxy(
    url: str,
    explicit_proxy: Mapping[str, object] | None = None,
    *,
    system_proxies: Mapping[str, str] | None = None,
) -> dict[str, str] | None:
    if _is_local_url(url):
        return None

    normalized_explicit = _normalize_proxy(explicit_proxy)
    if normalized_explicit is not None:
        return normalized_explicit

    if _should_bypass_proxy(url):
        return None

    configured_proxy = _normalize_proxy_server(
        getattr(settings, "outbound_proxy_url", None),
    )
    if configured_proxy is not None:
        return {"server": configured_proxy}

    if not bool(getattr(settings, "use_system_proxy", True)):
        return None

    proxies = dict(system_proxies) if system_proxies is not None else getproxies()
    scheme = (urlparse(url).scheme or "http").lower()
    server = _normalize_proxy_server(proxies.get(scheme) or proxies.get("all"))
    return {"server": server} if server is not None else None


def _should_bypass_proxy(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return True

    raw_no_proxy = str(getattr(settings, "outbound_no_proxy", "") or "")
    for raw_pattern in raw_no_proxy.split(","):
        pattern = raw_pattern.strip().lower().lstrip(".").rstrip(".")
        if not pattern:
            continue
        if host == pattern or host.endswith(f".{pattern}"):
            return True
    return False


def _is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").strip().lower().rstrip(".")
    if not host or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _normalize_proxy(
    proxy: Mapping[str, object] | None,
) -> dict[str, str] | None:
    if proxy is None:
        return None
    server = _normalize_proxy_server(proxy.get("server"))
    if server is None:
        return None
    normalized = {"server": server}
    username = proxy.get("username")
    password = proxy.get("password")
    if isinstance(username, str) and username:
        normalized["username"] = username
    if isinstance(password, str) and password:
        normalized["password"] = password
    return normalized


def _normalize_proxy_server(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    server = value.strip()
    if "://" not in server:
        server = f"http://{server}"
    parsed = urlparse(server)
    if parsed.scheme not in {"http", "https", "socks5"} or not parsed.hostname:
        return None
    return server


def _build_httpx_proxy(
    proxy: Mapping[str, str] | None,
) -> str | httpx.Proxy | None:
    if proxy is None:
        return None
    server = proxy.get("server")
    if not server:
        return None
    username = proxy.get("username")
    password = proxy.get("password")
    if username:
        return httpx.Proxy(server, auth=(username, password or ""))
    return server


def _build_playwright_proxy(proxy: Mapping[str, object] | None) -> dict[str, str] | None:
    if proxy is None:
        return None
    server = proxy.get("server")
    if not isinstance(server, str) or not server.strip():
        return None
    out: dict[str, str] = {"server": server.strip()}
    username = proxy.get("username")
    password = proxy.get("password")
    if isinstance(username, str) and username:
        out["username"] = username
    if isinstance(password, str) and password:
        out["password"] = password
    return out


def _coerce_response_url(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if hasattr(value, "human_repr"):
        human_repr = getattr(value, "human_repr")
        if callable(human_repr):
            rendered = human_repr()
            if isinstance(rendered, str):
                return rendered
    return str(value) if value is not None else None


def _assert_safe_httpx_response(response: object) -> None:
    history = getattr(response, "history", [])
    for item in list(history) + [response]:
        candidate = _coerce_response_url(getattr(item, "url", None))
        if candidate:
            assert_safe_outbound_url(candidate)


async def _attach_safe_route_guard(context) -> None:
    async def _guard(route) -> None:
        request = route.request
        candidate = getattr(request, "url", None)
        if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
            try:
                assert_safe_outbound_url(candidate)
            except UnsafeTargetError:
                await route.abort("blockedbyclient")
                return
        await route.continue_()

    await context.route("**/*", _guard)


def _assert_safe_playwright_page(page) -> None:
    candidate = getattr(page, "url", None)
    if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
        assert_safe_outbound_url(candidate)


def _resolve_session_cache_options(
    login_flow: Mapping[str, object] | None,
) -> tuple[str | None, int]:
    if login_flow is None:
        return None, 1800
    cache_key_raw = login_flow.get("session_key")
    cache_key = cache_key_raw.strip()[:128] if isinstance(cache_key_raw, str) and cache_key_raw.strip() else None
    ttl_raw = login_flow.get("session_ttl_sec")
    ttl_sec = 1800
    if isinstance(ttl_raw, (int, float)):
        ttl_sec = int(ttl_raw)
    ttl_sec = max(60, min(86_400, ttl_sec))
    return cache_key, ttl_sec


async def _get_cached_storage_state(cache_key: str | None) -> dict[str, object] | None:
    if not cache_key:
        return None
    now = time.monotonic()
    async with _LOGIN_STORAGE_CACHE_LOCK:
        item = _LOGIN_STORAGE_CACHE.get(cache_key)
        if item is None:
            return None
        expires_at, state = item
        if expires_at <= now:
            _LOGIN_STORAGE_CACHE.pop(cache_key, None)
            return None
        return dict(state)


async def _set_cached_storage_state(
    *,
    cache_key: str,
    state: dict[str, object],
    ttl_sec: int,
) -> None:
    if not cache_key:
        return
    expires_at = time.monotonic() + ttl_sec
    async with _LOGIN_STORAGE_CACHE_LOCK:
        _LOGIN_STORAGE_CACHE[cache_key] = (expires_at, dict(state))


async def _is_cached_login_session_valid(
    *,
    page,
    target_url: str,
    login_flow: Mapping[str, object],
    default_timeout_ms: int,
) -> bool:
    check_selector = login_flow.get("session_check_selector")
    if not isinstance(check_selector, str) or not check_selector.strip():
        return True
    check_url_raw = login_flow.get("session_check_url")
    check_url = check_url_raw.strip() if isinstance(check_url_raw, str) and check_url_raw.strip() else target_url
    check_url = assert_safe_outbound_url(check_url)
    timeout_ms = _bounded_timeout(login_flow.get("timeout_ms"), default_timeout_ms)
    timeout_ms = min(timeout_ms, 6_000)
    try:
        await page.goto(
            check_url,
            timeout=timeout_ms,
            wait_until="domcontentloaded",
        )
        _assert_safe_playwright_page(page)
        await page.wait_for_selector(check_selector.strip(), timeout=timeout_ms)
        return True
    except (PlaywrightTimeoutError, PlaywrightError):
        return False


async def _run_login_flow(
    *,
    page,
    target_url: str,
    login_flow: Mapping[str, object],
    default_timeout_ms: int,
) -> None:
    flow_timeout = _bounded_timeout(login_flow.get("timeout_ms"), default_timeout_ms)
    login_url = login_flow.get("url")
    if isinstance(login_url, str) and login_url.strip():
        safe_login_url = assert_safe_outbound_url(login_url.strip())
        await page.goto(
            safe_login_url,
            timeout=flow_timeout,
            wait_until="domcontentloaded",
        )
        _assert_safe_playwright_page(page)
    else:
        await page.goto(
            target_url,
            timeout=flow_timeout,
            wait_until="domcontentloaded",
        )
        _assert_safe_playwright_page(page)

    values_raw = login_flow.get("values")
    values: Mapping[str, str] = values_raw if isinstance(values_raw, Mapping) else {}
    steps_raw = login_flow.get("steps")
    if not isinstance(steps_raw, list):
        return

    for step_raw in steps_raw:
        if not isinstance(step_raw, Mapping):
            continue
        action = str(step_raw.get("action") or "").strip().lower()
        timeout_ms = _bounded_timeout(step_raw.get("timeout_ms"), flow_timeout)
        if action == "goto":
            step_url = step_raw.get("url")
            if isinstance(step_url, str) and step_url.strip():
                safe_step_url = assert_safe_outbound_url(step_url.strip())
                await page.goto(
                    safe_step_url,
                    timeout=timeout_ms,
                    wait_until="domcontentloaded",
                )
                _assert_safe_playwright_page(page)
            continue
        if action == "fill":
            selector = step_raw.get("selector")
            if not isinstance(selector, str) or not selector.strip():
                raise ValueError("login_flow fill step requires selector")
            value = ""
            value_from = step_raw.get("value_from")
            if isinstance(value_from, str) and value_from in values:
                value = values[value_from]
            elif isinstance(step_raw.get("value"), str):
                value = str(step_raw.get("value"))
            await page.fill(selector.strip(), value, timeout=timeout_ms)
            continue
        if action == "click":
            selector = step_raw.get("selector")
            if not isinstance(selector, str) or not selector.strip():
                raise ValueError("login_flow click step requires selector")
            await page.click(selector.strip(), timeout=timeout_ms)
            continue
        if action == "wait_for_selector":
            selector = step_raw.get("selector")
            if not isinstance(selector, str) or not selector.strip():
                raise ValueError("login_flow wait_for_selector step requires selector")
            await page.wait_for_selector(selector.strip(), timeout=timeout_ms)
            continue
        if action == "wait_for_load_state":
            wait_until = str(step_raw.get("wait_until") or "networkidle").strip().lower()
            if wait_until not in {"load", "domcontentloaded", "networkidle"}:
                wait_until = "networkidle"
            await page.wait_for_load_state(wait_until, timeout=timeout_ms)
            continue
        if action == "sleep":
            ms_raw = step_raw.get("ms")
            ms = 0
            if isinstance(ms_raw, (int, float)):
                ms = int(ms_raw)
            await page.wait_for_timeout(max(0, min(60_000, ms)))
            continue

    success_selector = login_flow.get("success_selector")
    if isinstance(success_selector, str) and success_selector.strip():
        await page.wait_for_selector(success_selector.strip(), timeout=flow_timeout)


def _bounded_timeout(raw_value: object, default_timeout: int) -> int:
    if isinstance(raw_value, (int, float)):
        return max(1_000, min(60_000, int(raw_value)))
    return max(1_000, min(60_000, int(default_timeout)))


async def _with_retry(operation, retries: int | None = None) -> str:
    max_retries = retries or settings.max_retry
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await operation()
        except (httpx.HTTPError, PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
            last_exception = exc
            if attempt == max_retries:
                break
            await asyncio.sleep(min(attempt, 3))

    assert last_exception is not None
    raise last_exception
