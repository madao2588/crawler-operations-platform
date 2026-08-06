import json
import re
from collections.abc import Mapping
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from lxml import html as lxml_html
from readability import Document

from app.utils.notice import (
    PROJECT_NOTICE_CATEGORIES,
    PROJECT_NOTICE_IRRELEVANCE_KEYWORDS,
    PROJECT_NOTICE_METADATA_KINDS,
    PROJECT_NOTICE_RELEVANCE_CONTEXT_KEYWORDS,
)


def parse_with_rules(html: str, rules: Mapping[str, str]) -> dict[str, str | None]:
    list_item_rule = rules.get("list_item")
    fields_rule = rules.get("fields")
    if list_item_rule and isinstance(fields_rule, Mapping):
        return _parse_list_items(html, list_item_rule, fields_rule)

    title_rule = rules.get("title")
    published_at_rule = rules.get("published_at")
    content_rule = rules.get("content")

    title = _extract_text(html, title_rule) if title_rule else None
    published_at = _extract_text(html, published_at_rule) if published_at_rule else None
    content_html = _extract_html(html, content_rule) if content_rule else None

    return {
        "title": title,
        "published_at": published_at,
        "content_html": content_html,
    }


def _parse_list_items(
    html: str,
    list_item_rule: str,
    fields_rule: Mapping[str, str],
) -> dict[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(list_item_rule)
    if not items:
        return {
            "title": None,
            "content_html": None,
        }

    normalized_entries: list[dict[str, str]] = []
    for item in items:
        entry: dict[str, str] = {}
        for field_name, selector in fields_rule.items():
            if not isinstance(selector, str) or not selector.strip():
                continue
            value = _extract_from_node(item, selector.strip())
            if value:
                entry[field_name] = value
        if entry:
            normalized_entries.append(entry)

    if not normalized_entries:
        return {
            "title": None,
            "content_html": None,
        }

    title = _derive_list_title(normalized_entries)
    content_html = _build_list_content_html(normalized_entries)
    return {
        "title": title,
        "content_html": content_html,
    }


def parse_with_readability(html: str) -> dict[str, str | None]:
    document = Document(html)
    title = document.short_title() or document.title()
    content_html = document.summary(html_partial=True)
    return {
        "title": title.strip() if title else None,
        "content_html": content_html,
    }


def extract_embedded_json_content(
    html: str,
    *,
    assignment: str,
    content_path: str,
    title_path: str | None = None,
) -> dict[str, str | None] | None:
    marker = re.search(
        rf"""(?:"|')?{re.escape(assignment)}(?:"|')?\s*:\s*""",
        html,
    )
    if marker is None:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(html[marker.end() :].lstrip())
    except (TypeError, ValueError):
        return None

    def value_at_path(path: str | None) -> object:
        current: object = payload
        if not path:
            return None
        for segment in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
        return current

    content_value = value_at_path(content_path)
    if not isinstance(content_value, str) or not content_value.strip():
        return None
    title_value = value_at_path(title_path)
    return {
        "title": (
            " ".join(title_value.split())
            if isinstance(title_value, str) and title_value.strip()
            else None
        ),
        "content_html": content_value.strip(),
    }


def extract_embedded_content_url(
    html: str,
    base_url: str,
    selector: str,
) -> str | None:
    css_selector, attribute = _split_selector_and_attr(selector)
    if not css_selector or not attribute:
        return None
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(css_selector)
    if node is None:
        return None
    raw_url = node.get(attribute)
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None
    absolute = urljoin(base_url, raw_url.strip())
    return absolute if absolute.startswith(("http://", "https://")) else None


def _extract_text(html: str, selector: str) -> str | None:
    if selector.startswith("css:"):
        soup = BeautifulSoup(html, "html.parser")
        node = soup.select_one(selector.removeprefix("css:"))
        return node.get_text(" ", strip=True) if node else None

    if selector.startswith("xpath:"):
        tree = lxml_html.fromstring(html)
        nodes = tree.xpath(selector.removeprefix("xpath:"))
        if not nodes:
            return None
        node = nodes[0]
        if isinstance(node, str):
            return node.strip() or None
        return " ".join(node.itertext()).strip() or None

    raise ValueError(f"Unsupported selector format: {selector}")


def _extract_html(html: str, selector: str) -> str | None:
    if selector.startswith("css:"):
        soup = BeautifulSoup(html, "html.parser")
        node = soup.select_one(selector.removeprefix("css:"))
        return str(node) if node else None

    if selector.startswith("xpath:"):
        tree = lxml_html.fromstring(html)
        nodes = tree.xpath(selector.removeprefix("xpath:"))
        if not nodes:
            return None
        node = nodes[0]
        if isinstance(node, str):
            return node.strip() or None
        return lxml_html.tostring(node, encoding="unicode")

    raise ValueError(f"Unsupported selector format: {selector}")


def _extract_from_node(node, selector: str) -> str | None:
    css_selector, attribute = _split_selector_and_attr(selector)
    target = node.select_one(css_selector)
    if target is None:
        return None

    if attribute is not None:
        value = target.get(attribute)
        if value is None:
            return None
        return " ".join(value) if isinstance(value, list) else str(value).strip()

    return target.get_text(" ", strip=True) or None


def _split_selector_and_attr(selector: str) -> tuple[str, str | None]:
    if "@" not in selector:
        return selector, None

    css_selector, attribute = selector.rsplit("@", 1)
    attribute = attribute.strip()
    if not css_selector.strip() or not attribute:
        return selector, None
    return css_selector.strip(), attribute


CRAWL_META_KEYS = frozenset(
    {
        "crawl_mode",
        "collection_mode",
        "allowed_hosts",
        "list_item",
        "detail_link",
        "detail_include_keywords",
        "detail_required_context_keywords",
        "detail_exclude_keywords",
        "max_items",
        "same_host_only",
        "list_page_urls",
        "list_page_urls_only",
        "list_url_template",
        "list_page_from",
        "list_page_to",
        "max_list_pages",
        "list_next_page",
        "list_json_items",
        "list_json_url_field",
        "list_json_title_field",
        "list_delay_ms",
        "detail_retries",
        "detail_retry_backoff_ms",
        "detail_retry_policy",
        "retry_policy",
        "detail_delay_ms",
        "request_timeout_sec",
        "fetch_timeout_sec",
        "force_dynamic_fetch",
        "dynamic_wait_selector",
        "prefer_list_title",
        "http_headers",
        "user_agent",
        "http_cookies",
        "cookie_domain",
        "login_flow",
        "login_username",
        "login_password",
        "login_values",
        "login_session_key",
        "login_session_ttl_sec",
        "anti_bot_challenge_keywords",
        "anti_bot_valid_selector",
        "anti_bot_block_status_codes",
        "anti_bot_block_backoff_ms",
        "anti_bot_retry_on_block",
        "embedded_content_url",
        "embedded_content_json_assignment",
        "embedded_content_json_path",
        "embedded_content_title_path",
        "proxy_server",
        "proxy_url",
        "proxy_username",
        "proxy_password",
        "proxy_on_block_only",
        "proxy_failover_enabled",
    }
)

MAX_LIST_PAGES_HARD = 50
PER_PAGE_DETAIL_SAFETY = 500
DETAIL_RETRY_MAX = 3


def _coerce_int(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def detail_url_limit(rules: Mapping[str, object]) -> int:
    """Upper bound on detail URLs to collect for list_follow (``max_items``)."""
    raw = rules.get("max_items", 20)
    try:
        return max(1, min(200, int(raw)))
    except (TypeError, ValueError):
        return 20


def list_page_fetch_budget(rules: Mapping[str, object]) -> int:
    """Max list-page HTTP fetches for list_follow (``max_list_pages``, cap 50)."""
    return max(1, min(MAX_LIST_PAGES_HARD, _coerce_int(rules.get("max_list_pages"), 30)))


def list_request_delay_seconds(rules: Mapping[str, object]) -> float:
    """Pause between list-page requests (``list_delay_ms``), up to 60s."""
    ms = max(0, min(60_000, _coerce_int(rules.get("list_delay_ms"), 0)))
    return ms / 1000.0


def detail_retry_count(rules: Mapping[str, object] | None) -> int:
    """Extra detail fetch attempts after the first failure (``detail_retries``, 0–3)."""
    if rules is None:
        return 0
    return max(0, min(DETAIL_RETRY_MAX, _coerce_int(rules.get("detail_retries"), 0)))


def detail_retry_sleep_seconds(rules: Mapping[str, object] | None, attempt_index: int) -> float:
    """Backoff before the next detail attempt (exponential, cap 30s)."""
    base_ms = 800
    if rules is not None:
        base_ms = max(200, min(30_000, _coerce_int(rules.get("detail_retry_backoff_ms"), 800)))
    factor = min(8, 2 ** min(3, max(0, attempt_index)))
    return min(30.0, (base_ms * factor) / 1000.0)


def detail_retry_policy(rules: Mapping[str, object] | None) -> str:
    """``all`` = retry on any failure; ``transient`` = 5xx / 429 / timeouts / network only."""
    if rules is None:
        return "all"
    raw = rules.get("detail_retry_policy", rules.get("retry_policy"))
    if not isinstance(raw, str):
        return "all"
    v = raw.strip().lower()
    if v in ("transient", "5xx", "timeout", "timeouts", "network", "safe"):
        return "transient"
    return "all"


def should_retry_detail_failure(exc: BaseException, policy: str) -> bool:
    if policy != "transient":
        return True

    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code if exc.response is not None else 0
        return code >= 500 or code == 429

    try:
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    except ImportError:
        return False
    return isinstance(exc, PlaywrightTimeoutError)


def detail_request_delay_seconds(rules: Mapping[str, object] | None) -> float:
    """Pause between detail-page requests (``detail_delay_ms``), up to 60s."""
    if rules is None:
        return 0.0
    ms = max(0, min(60_000, _coerce_int(rules.get("detail_delay_ms"), 0)))
    return ms / 1000.0


def fetch_timeout_seconds(rules: Mapping[str, object] | None, default: float) -> float:
    """HTTP / browser navigation timeout (``request_timeout_sec`` or ``fetch_timeout_sec``)."""
    if rules is None:
        return default
    raw = rules.get("request_timeout_sec", rules.get("fetch_timeout_sec"))
    if raw is None:
        return default
    try:
        v = float(raw)
        return max(5.0, min(120.0, v))
    except (TypeError, ValueError):
        return default


def fetch_http_headers(rules: Mapping[str, object] | None) -> dict[str, str] | None:
    """Extra request headers: ``http_headers`` first, then ``user_agent`` overrides UA."""
    if rules is None:
        return None
    out: dict[str, str] = {}
    raw = rules.get("http_headers")
    if isinstance(raw, dict):
        count = 0
        for k, v in raw.items():
            if count >= 20:
                break
            if not isinstance(k, str) or not k.strip():
                continue
            if isinstance(v, str):
                val = v[:4096]
            elif isinstance(v, (int, float, bool)):
                val = str(v)[:4096]
            else:
                continue
            out[k.strip()] = val
            count += 1
    ua = rules.get("user_agent")
    if isinstance(ua, str) and ua.strip():
        out["User-Agent"] = ua.strip()[:1024]
    return out or None


def fetch_http_cookies(rules: Mapping[str, object] | None) -> dict[str, str] | None:
    """Cookie jar for requests (``http_cookies`` object). Values are sensitive when stored in tasks."""
    if rules is None:
        return None
    raw = rules.get("http_cookies")
    if not isinstance(raw, dict):
        return None
    out: dict[str, str] = {}
    count = 0
    for k, v in raw.items():
        if count >= 40:
            break
        if not isinstance(k, str) or not k.strip():
            continue
        name = k.strip()[:128]
        if isinstance(v, str):
            val = v[:8192]
        elif isinstance(v, (int, float, bool)):
            val = str(v)[:8192]
        else:
            continue
        out[name] = val
        count += 1
    return out or None


def fetch_cookie_domain_override(rules: Mapping[str, object] | None) -> str | None:
    """Optional Playwright cookie ``domain`` (``cookie_domain``); see Playwright cookie rules."""
    if rules is None:
        return None
    d = rules.get("cookie_domain")
    if isinstance(d, str) and d.strip():
        return d.strip()[:256]
    return None


def fetch_login_flow(rules: Mapping[str, object] | None) -> dict[str, object] | None:
    """Optional browser login workflow (``login_flow``) for dynamic fetches.

    Accepted shape:
    {
      "url": "https://example.com/login",
      "steps": [
        {"action": "fill", "selector": "#user", "value_from": "login_username"},
        {"action": "fill", "selector": "#pass", "value_from": "login_password"},
        {"action": "click", "selector": "button[type=submit]"},
        {"action": "wait_for_selector", "selector": ".dashboard"},
      ],
      "success_selector": ".dashboard"
    }
    """
    if rules is None:
        return None
    raw = rules.get("login_flow")
    if not isinstance(raw, dict):
        return None

    out: dict[str, object] = {}
    login_url = raw.get("url")
    if isinstance(login_url, str) and login_url.strip():
        out["url"] = login_url.strip()[:2048]

    success_selector = raw.get("success_selector")
    if isinstance(success_selector, str) and success_selector.strip():
        out["success_selector"] = success_selector.strip()[:512]

    timeout_raw = raw.get("timeout_ms")
    timeout_ms = _coerce_int(timeout_raw, 15_000) if timeout_raw is not None else 15_000
    out["timeout_ms"] = max(1_000, min(60_000, timeout_ms))

    session_key = rules.get("login_session_key")
    if isinstance(session_key, str) and session_key.strip():
        out["session_key"] = session_key.strip()[:128]
    ttl_raw = rules.get("login_session_ttl_sec")
    ttl_sec = _coerce_int(ttl_raw, 1800) if ttl_raw is not None else 1800
    out["session_ttl_sec"] = max(60, min(86_400, ttl_sec))

    session_check_selector = raw.get("session_check_selector")
    if isinstance(session_check_selector, str) and session_check_selector.strip():
        out["session_check_selector"] = session_check_selector.strip()[:512]
    session_check_url = raw.get("session_check_url")
    if isinstance(session_check_url, str) and session_check_url.strip():
        out["session_check_url"] = session_check_url.strip()[:2048]

    values: dict[str, str] = {}
    username = rules.get("login_username")
    password = rules.get("login_password")
    if isinstance(username, str) and username:
        values["login_username"] = username[:1024]
    if isinstance(password, str) and password:
        values["login_password"] = password[:1024]
    login_values_raw = rules.get("login_values")
    if isinstance(login_values_raw, dict):
        count = 0
        for k, v in login_values_raw.items():
            if count >= 20:
                break
            if not isinstance(k, str) or not k.strip():
                continue
            if isinstance(v, str):
                values[k.strip()[:128]] = v[:2048]
                count += 1
    out["values"] = values

    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list):
        return None
    steps: list[dict[str, object]] = []
    for step_raw in steps_raw[:20]:
        if not isinstance(step_raw, dict):
            continue
        action_raw = step_raw.get("action")
        if not isinstance(action_raw, str):
            continue
        action = action_raw.strip().lower()
        if action not in {
            "goto",
            "fill",
            "click",
            "wait_for_selector",
            "wait_for_load_state",
            "sleep",
        }:
            continue

        step: dict[str, object] = {"action": action}
        selector = step_raw.get("selector")
        if isinstance(selector, str) and selector.strip():
            step["selector"] = selector.strip()[:512]
        url_value = step_raw.get("url")
        if isinstance(url_value, str) and url_value.strip():
            step["url"] = url_value.strip()[:2048]
        value_from = step_raw.get("value_from")
        if isinstance(value_from, str) and value_from.strip():
            step["value_from"] = value_from.strip()[:128]
        value = step_raw.get("value")
        if isinstance(value, str):
            step["value"] = value[:2048]
        wait_until = step_raw.get("wait_until")
        if isinstance(wait_until, str) and wait_until.strip():
            step["wait_until"] = wait_until.strip().lower()[:64]
        timeout_step_raw = step_raw.get("timeout_ms")
        if timeout_step_raw is not None:
            timeout_step = _coerce_int(timeout_step_raw, 15_000)
            step["timeout_ms"] = max(1_000, min(60_000, timeout_step))
        sleep_step_raw = step_raw.get("ms")
        if sleep_step_raw is not None:
            sleep_ms = _coerce_int(sleep_step_raw, 0)
            step["ms"] = max(0, min(60_000, sleep_ms))
        steps.append(step)

    if not steps:
        return None
    out["steps"] = steps
    return out


def anti_bot_block_status_codes(rules: Mapping[str, object] | None) -> set[int]:
    """HTTP status codes considered anti-bot blocking (default: 403/429)."""
    if rules is None:
        return {403, 429}
    raw = rules.get("anti_bot_block_status_codes")
    if not isinstance(raw, list):
        return {403, 429}
    out: set[int] = set()
    for item in raw[:10]:
        try:
            code = int(item)
        except (TypeError, ValueError):
            continue
        if 300 <= code <= 599:
            out.add(code)
    return out or {403, 429}


def anti_bot_block_backoff_seconds(rules: Mapping[str, object] | None) -> float:
    """Extra wait before dynamic fallback after static block status (0-30s)."""
    if rules is None:
        return 0.0
    ms = max(0, min(30_000, _coerce_int(rules.get("anti_bot_block_backoff_ms"), 0)))
    return ms / 1000.0


def anti_bot_retry_on_block(rules: Mapping[str, object] | None) -> bool:
    """Whether anti-bot challenge pages should raise retryable errors (default true)."""
    if rules is None:
        return True
    raw = rules.get("anti_bot_retry_on_block")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return True


def anti_bot_challenge_keywords(rules: Mapping[str, object] | None) -> list[str]:
    """Case-insensitive challenge markers searched in HTML."""
    defaults = [
        "captcha",
        "verify you are human",
        "access denied",
        "too many requests",
        "cloudflare",
        "机器人验证",
        "安全验证",
    ]
    if rules is None:
        return defaults
    raw = rules.get("anti_bot_challenge_keywords")
    if not isinstance(raw, list):
        return defaults
    out: list[str] = []
    for item in raw[:20]:
        if isinstance(item, str) and item.strip():
            out.append(item.strip().lower()[:128])
    return out or defaults


def _string_list(value: object, *, limit: int = 50) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:limit]:
        if isinstance(item, str) and item.strip():
            out.append(item.strip().lower())
    return out


def _matches_detail_link_filters(
    match_blob: str,
    rules: Mapping[str, object],
) -> bool:
    """Apply shared list-link relevance rules to HTML and JSON sources."""
    normalized = match_blob.lower()
    include_keywords = _string_list(rules.get("detail_include_keywords"))
    required_context_keywords = _string_list(
        rules.get("detail_required_context_keywords")
    )
    exclude_keywords = _string_list(rules.get("detail_exclude_keywords"))
    metadata = rules.get("metadata")
    metadata_kind = (
        str(metadata.get("kind") or "").strip().lower()
        if isinstance(metadata, Mapping)
        else ""
    )
    is_project_notice = (
        str(rules.get("category") or "").strip() in PROJECT_NOTICE_CATEGORIES
        or metadata_kind in PROJECT_NOTICE_METADATA_KINDS
    )
    if is_project_notice:
        if not required_context_keywords:
            required_context_keywords = _string_list(
                list(PROJECT_NOTICE_RELEVANCE_CONTEXT_KEYWORDS)
            )
        exclude_keywords = list(
            dict.fromkeys(
                [
                    *exclude_keywords,
                    *_string_list(list(PROJECT_NOTICE_IRRELEVANCE_KEYWORDS)),
                ]
            )
        )

    if include_keywords and not any(
        keyword in normalized for keyword in include_keywords
    ):
        return False
    if required_context_keywords and not any(
        keyword in normalized for keyword in required_context_keywords
    ):
        return False
    if exclude_keywords and any(
        keyword in normalized for keyword in exclude_keywords
    ):
        return False
    return True


def looks_like_anti_bot_challenge(html: str, rules: Mapping[str, object] | None) -> bool:
    """Heuristic challenge-page detection by configurable keywords."""
    if not html:
        return False
    valid_selector = (
        rules.get("anti_bot_valid_selector")
        if isinstance(rules, Mapping)
        else None
    )
    if isinstance(valid_selector, str) and valid_selector.strip():
        try:
            if BeautifulSoup(html, "html.parser").select_one(valid_selector.strip()):
                return False
        except Exception:
            pass
    text = html.lower()[:200_000]
    for kw in anti_bot_challenge_keywords(rules):
        if kw and kw in text:
            return True
    return False


def fetch_proxy_config(rules: Mapping[str, object] | None) -> dict[str, object] | None:
    """Optional proxy config for dynamic fetches.

    Supports:
    - ``proxy_server`` / ``proxy_url``: e.g. ``http://host:port``
    - ``proxy_username`` / ``proxy_password``
    - ``proxy_on_block_only`` (default: true)
    - ``proxy_failover_enabled`` (default: true)
    """
    if rules is None:
        return None
    server_raw = rules.get("proxy_server", rules.get("proxy_url"))
    if not isinstance(server_raw, str) or not server_raw.strip():
        return None
    server = server_raw.strip()[:2048]

    out: dict[str, object] = {"server": server}
    user_raw = rules.get("proxy_username")
    if isinstance(user_raw, str) and user_raw:
        out["username"] = user_raw[:256]
    pass_raw = rules.get("proxy_password")
    if isinstance(pass_raw, str) and pass_raw:
        out["password"] = pass_raw[:512]

    on_block_only_raw = rules.get("proxy_on_block_only")
    on_block_only = True
    if isinstance(on_block_only_raw, bool):
        on_block_only = on_block_only_raw
    elif isinstance(on_block_only_raw, str):
        on_block_only = on_block_only_raw.strip().lower() in {"1", "true", "yes", "on"}
    out["on_block_only"] = on_block_only

    failover_raw = rules.get("proxy_failover_enabled")
    failover = True
    if isinstance(failover_raw, bool):
        failover = failover_raw
    elif isinstance(failover_raw, str):
        failover = failover_raw.strip().lower() in {"1", "true", "yes", "on"}
    out["failover_enabled"] = failover
    return out


def resolve_list_page_urls(start_url: str, rules: Mapping[str, object]) -> list[str]:
    """Ordered unique list-page URLs: start_url, optional extras, optional template range."""
    ordered: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = u.strip()
        if not u.startswith(("http://", "https://")):
            return
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    if rules.get("list_page_urls_only") is not True:
        add(start_url)

    raw_extra = rules.get("list_page_urls")
    if isinstance(raw_extra, list):
        for item in raw_extra:
            if isinstance(item, str):
                add(item)

    tmpl = rules.get("list_url_template")
    if isinstance(tmpl, str) and "{page}" in tmpl:
        p_from = max(1, _coerce_int(rules.get("list_page_from"), 1))
        p_to = _coerce_int(rules.get("list_page_to"), p_from)
        if p_to < p_from:
            p_to = p_from
        max_pages = list_page_fetch_budget(rules)
        generated = 0
        for page in range(p_from, p_to + 1):
            if generated >= max_pages:
                break
            add(tmpl.replace("{page}", str(page)))
            generated += 1

    return ordered


def extract_next_list_page_url(html: str, current_list_url: str, rules: Mapping[str, object]) -> str | None:
    """Resolve next list-page URL from full HTML (``list_next_page`` selector)."""
    rule = rules.get("list_next_page")
    if not isinstance(rule, str) or not rule.strip():
        return None

    sel = rule.strip()
    if "@" not in sel:
        sel = f"{sel}@href"
    css_sel, attr = _split_selector_and_attr(sel)
    if not css_sel or attr is None:
        return None

    soup = BeautifulSoup(html, "html.parser")
    target = soup.select_one(css_sel)
    if target is None:
        return None
    raw_href = target.get(attr)
    if not raw_href:
        return None
    href = str(raw_href).strip()
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return None

    absolute = urljoin(current_list_url, href)
    parsed_u = urlparse(absolute)
    base_host = urlparse(current_list_url).netloc

    same_host_only = rules.get("same_host_only", True)
    if isinstance(same_host_only, str):
        same_host_only = same_host_only.strip().lower() in ("1", "true", "yes", "on")

    if same_host_only and base_host and parsed_u.netloc and parsed_u.netloc != base_host:
        return None

    if absolute.rstrip("/") == current_list_url.rstrip("/"):
        return None

    return absolute


def strip_meta_for_detail_parse(rules: Mapping[str, object]) -> dict[str, str]:
    """Strip list-discovery keys so detail pages parse with title/content rules only."""
    out: dict[str, str] = {}
    for key, value in rules.items():
        if key in CRAWL_META_KEYS or key == "fields":
            continue
        if isinstance(value, str) and value.strip():
            out[str(key)] = value
    return out


def detail_rules_json(rules: Mapping[str, object]) -> str | None:
    stripped = strip_meta_for_detail_parse(rules)
    if not stripped:
        return None
    return json.dumps(stripped, ensure_ascii=False)


def _link_target_for_item(item, link_selector: str):
    css_sel, attr = _split_selector_and_attr(link_selector)
    if not css_sel or attr is None:
        return None, None
    if css_sel == ":scope":
        return item, attr
    return item.select_one(css_sel), attr


def _extract_url_candidate(raw_value: str) -> str:
    value = raw_value.strip()
    if value.startswith(("http://", "https://", "/", "../", "./")):
        return value

    match = re.search(r"""["'](?P<url>(?:https?://|/|\.\.?/)[^"']+)["']""", value)
    if match:
        return match.group("url").strip()
    return value


def extract_list_follow_urls(
    html: str,
    base_url: str,
    rules: Mapping[str, object],
    *,
    url_cap: int | None = None,
) -> list[str]:
    return [
        item["url"]
        for item in extract_list_follow_items(
            html,
            base_url,
            rules,
            url_cap=url_cap,
        )
    ]


def extract_list_follow_items(
    html: str,
    base_url: str,
    rules: Mapping[str, object],
    *,
    url_cap: int | None = None,
) -> list[dict[str, str]]:
    """Collect absolute detail URLs from one list page (crawl_mode=list_follow).

    ``url_cap`` caps how many new URLs to return this page (for multi-list aggregation).
    """
    if isinstance(rules.get("list_json_items"), str):
        return _extract_json_list_follow_items(
            html,
            base_url,
            rules,
            url_cap=url_cap,
        )

    list_item_rule = rules.get("list_item")
    detail_link_rule = rules.get("detail_link")
    if not isinstance(list_item_rule, str) or not list_item_rule.strip():
        return []
    if not isinstance(detail_link_rule, str) or not detail_link_rule.strip():
        return []

    rules_max = detail_url_limit(rules)

    if url_cap is not None:
        try:
            cap = max(0, int(url_cap))
        except (TypeError, ValueError):
            cap = rules_max
        max_items = min(PER_PAGE_DETAIL_SAFETY, cap)
    else:
        max_items = rules_max

    same_host_only = rules.get("same_host_only", True)
    if isinstance(same_host_only, str):
        same_host_only = same_host_only.strip().lower() in ("1", "true", "yes", "on")

    base_host = urlparse(base_url).netloc

    soup = BeautifulSoup(html, "html.parser")
    items = soup.select(list_item_rule.strip())

    link_sel = detail_link_rule.strip()
    if "@" not in link_sel:
        link_sel = f"{link_sel}@href"

    items_out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if len(items_out) >= max_items:
            break
        target, attr = _link_target_for_item(item, link_sel)
        if target is None:
            continue
        raw_href = target.get(attr)
        if not raw_href:
            continue
        href = _extract_url_candidate(str(raw_href))
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute = urljoin(base_url, href)
        match_blob = " ".join(
            [
                item.get_text(" ", strip=True),
                target.get_text(" ", strip=True),
                href,
                absolute,
            ]
        )
        if not _matches_detail_link_filters(match_blob, rules):
            continue
        parsed_u = urlparse(absolute)
        if same_host_only and base_host and parsed_u.netloc and parsed_u.netloc != base_host:
            continue
        if absolute not in seen:
            seen.add(absolute)
            detail: dict[str, str] = {"url": absolute}
            title = _extract_list_item_title(item, target)
            if title:
                detail["title"] = title
            items_out.append(detail)

    return items_out


def _extract_json_list_follow_items(
    payload_text: str,
    base_url: str,
    rules: Mapping[str, object],
    *,
    url_cap: int | None,
) -> list[dict[str, str]]:
    items_path = str(rules.get("list_json_items") or "").strip()
    url_field = str(rules.get("list_json_url_field") or "").strip()
    title_field = str(rules.get("list_json_title_field") or "").strip()
    if not items_path or not url_field:
        return []
    try:
        payload: object = json.loads(payload_text)
    except (TypeError, ValueError):
        return []
    current = payload
    for segment in items_path.split("."):
        if not isinstance(current, dict):
            return []
        current = current.get(segment)
    if not isinstance(current, list):
        return []

    rules_max = detail_url_limit(rules)
    if url_cap is not None:
        try:
            cap = max(0, int(url_cap))
        except (TypeError, ValueError):
            cap = rules_max
        max_items = min(PER_PAGE_DETAIL_SAFETY, cap)
    else:
        max_items = rules_max

    same_host_only = rules.get("same_host_only", True)
    if isinstance(same_host_only, str):
        same_host_only = same_host_only.strip().lower() in ("1", "true", "yes", "on")
    base_host = urlparse(base_url).netloc
    items_out: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_item in current:
        if len(items_out) >= max_items:
            break
        if not isinstance(raw_item, dict):
            continue
        raw_url = raw_item.get(url_field)
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue
        absolute = urljoin(base_url, raw_url.strip())
        title_value = raw_item.get(title_field) if title_field else None
        title = " ".join(str(title_value or "").split())
        match_blob = f"{title} {raw_url} {absolute}"
        if not _matches_detail_link_filters(match_blob, rules):
            continue
        parsed_u = urlparse(absolute)
        if same_host_only and base_host and parsed_u.netloc and parsed_u.netloc != base_host:
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        detail = {"url": absolute}
        if title:
            detail["title"] = title
        items_out.append(detail)
    return items_out


def _extract_list_item_title(item, target) -> str | None:
    candidates = [
        target.get("title"),
        target.get("aria-label"),
        target.get_text(" ", strip=True),
        item.get("title"),
        item.get_text(" ", strip=True),
    ]
    for raw in candidates:
        value = " ".join(str(raw or "").split())
        if value:
            return value
    return None


def _derive_list_title(entries: list[dict[str, str]]) -> str:
    preferred_fields = ("title", "topic", "name", "headline")
    for field in preferred_fields:
        for entry in entries:
            value = entry.get(field)
            if value:
                return value

    first_entry = entries[0]
    return next(iter(first_entry.values()), "Collected Items")


def _build_list_content_html(entries: list[dict[str, str]]) -> str:
    blocks: list[str] = []
    for index, entry in enumerate(entries[:20], start=1):
        parts = [f'<article data-index="{index}">']
        for field_name, value in entry.items():
            label = field_name.replace("_", " ").strip() or "field"
            parts.append(
                f"<p><strong>{label}:</strong> {BeautifulSoup(value, 'html.parser').get_text(' ', strip=True)}</p>"
            )
        parts.append("</article>")
        blocks.append("".join(parts))
    return "".join(blocks)
