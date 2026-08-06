"""Unit tests for list_follow URL discovery (product multi-page collection)."""

import json

import httpx

from app.engine.parser import (
    anti_bot_block_backoff_seconds,
    anti_bot_block_status_codes,
    anti_bot_retry_on_block,
    anti_bot_challenge_keywords,
    detail_request_delay_seconds,
    detail_retry_count,
    detail_retry_policy,
    detail_retry_sleep_seconds,
    detail_rules_json,
    detail_url_limit,
    fetch_cookie_domain_override,
    fetch_http_cookies,
    fetch_http_headers,
    fetch_login_flow,
    fetch_proxy_config,
    fetch_timeout_seconds,
    extract_list_follow_urls,
    extract_list_follow_items,
    extract_embedded_json_content,
    extract_next_list_page_url,
    list_page_fetch_budget,
    list_request_delay_seconds,
    looks_like_anti_bot_challenge,
    resolve_list_page_urls,
    should_retry_detail_failure,
    strip_meta_for_detail_parse,
)
from app.engine.parser import parse_with_rules


def test_extract_list_follow_urls_absolute_and_relative() -> None:
    html = """
    <html><body>
      <div class="row"><a class="t" href="/p/1">One</a></div>
      <div class="row"><a class="t" href="https://other.example/x">Off</a></div>
      <div class="row"><a class="t" href="/p/2">Two</a></div>
    </body></html>
    """
    rules = {
        "crawl_mode": "list_follow",
        "list_item": ".row",
        "detail_link": "a.t@href",
        "same_host_only": True,
        "max_items": 10,
    }
    base = "https://news.example/list"
    urls = extract_list_follow_urls(html, base, rules)
    assert urls == [
        "https://news.example/p/1",
        "https://news.example/p/2",
    ]


def test_extract_list_follow_respects_max_items() -> None:
    parts = [f"<div class='i'><a href='/p/{n}'>x</a></div>" for n in range(5)]
    html = "".join(parts)
    rules = {
        "list_item": ".i",
        "detail_link": "a@href",
        "max_items": 2,
        "same_host_only": False,
    }
    urls = extract_list_follow_urls(html, "https://z.example/", rules)
    assert len(urls) == 2


def test_extract_list_follow_filters_detail_links_by_keywords() -> None:
    html = """
    <html><body>
      <a href="/notice/1">关于组织申报生物医药项目的通知</a>
      <a href="/notice/2">科技计划项目拟立项结果公示</a>
      <a href="/notice/3">人事任免公告</a>
    </body></html>
    """
    rules = {
        "list_item": "a",
        "detail_link": ":scope@href",
        "detail_include_keywords": ["申报", "结果公示", "拟立项"],
        "max_items": 10,
    }

    urls = extract_list_follow_urls(html, "https://gov.example/list", rules)

    assert urls == [
        "https://gov.example/notice/1",
        "https://gov.example/notice/2",
    ]


def test_extract_list_follow_reads_javascript_onclick_detail_url() -> None:
    html = """
    <table>
      <tr><td class="title"><div onclick="window.parent.openW('/notice/42.html')" title="项目申报通知">项目申报通知</div></td></tr>
    </table>
    """
    rules = {
        "list_item": "td.title",
        "detail_link": "div@onclick",
        "detail_include_keywords": ["申报"],
        "max_items": 10,
    }

    assert extract_list_follow_urls(html, "https://gov.example/list/", rules) == [
        "https://gov.example/notice/42.html"
    ]


def test_extract_list_follow_items_keeps_list_title_for_detail_page() -> None:
    html = """
    <table>
      <tr>
        <td class="title">
          <div onclick="window.parent.openW('/notice/42.html')" title="关于组织申报重点专项的通知">
            关于组织申报重点专项的通知
          </div>
        </td>
      </tr>
    </table>
    """
    rules = {
        "list_item": "td.title",
        "detail_link": "div@onclick",
        "detail_include_keywords": ["申报"],
        "max_items": 10,
    }

    assert extract_list_follow_items(html, "https://gov.example/list/", rules) == [
        {
            "url": "https://gov.example/notice/42.html",
            "title": "关于组织申报重点专项的通知",
        }
    ]


def test_extract_list_follow_items_supports_structured_json_feed() -> None:
    payload = json.dumps(
        {
            "articles": [
                {
                    "url": "http://gov.example/notices/1",
                    "title": "项目申报通知",
                },
                {
                    "url": "http://gov.example/notices/2",
                    "title": "人事任免公告",
                },
            ]
        },
        ensure_ascii=False,
    )
    rules = {
        "list_json_items": "articles",
        "list_json_url_field": "url",
        "list_json_title_field": "title",
        "detail_include_keywords": ["申报"],
        "max_items": 10,
    }

    assert extract_list_follow_items(
        payload,
        "https://gov.example/postmeta/notices.json",
        rules,
    ) == [
        {
            "url": "http://gov.example/notices/1",
            "title": "项目申报通知",
        }
    ]


def test_project_list_filter_requires_business_context_and_rejects_admissions() -> None:
    html = """
    <html><body>
      <a href="/notice/admission">关于2026年秋季公办中小学拟录取名单的公示</a>
      <a href="/notice/result">关于2026年度科技计划项目拟立项名单的公示</a>
      <a href="/notice/apply">关于组织申报2026年度重点研发计划项目的通知</a>
      <a href="/notice/general">关于办公场所调整的公示</a>
    </body></html>
    """
    rules = {
        "list_item": "a",
        "detail_link": ":scope@href",
        "detail_include_keywords": ["申报", "公示", "名单"],
        "detail_required_context_keywords": ["项目", "研发", "科技计划", "资金"],
        "detail_exclude_keywords": ["招生", "录取", "幼儿园", "中小学"],
        "max_items": 10,
    }

    assert extract_list_follow_urls(html, "https://gov.example/list", rules) == [
        "https://gov.example/notice/result",
        "https://gov.example/notice/apply",
    ]


def test_existing_project_task_rules_receive_relevance_defaults() -> None:
    html = """
    <html><body>
      <a href="/notice/admission">关于2026年秋季公办中小学拟录取名单的公示</a>
      <a href="/notice/result">关于科技计划项目拟立项名单的公示</a>
      <a href="/notice/general">关于办公场所调整的公示</a>
    </body></html>
    """
    legacy_rules = {
        "list_item": "a",
        "detail_link": ":scope@href",
        "detail_include_keywords": ["项目", "公示", "名单"],
        "detail_exclude_keywords": ["登录", "注册"],
        "category": "项目申报",
        "metadata": {"kind": "project_notice"},
        "max_items": 10,
    }

    assert extract_list_follow_urls(
        html,
        "https://gov.example/list",
        legacy_rules,
    ) == ["https://gov.example/notice/result"]


def test_project_json_feed_uses_the_same_relevance_filter() -> None:
    payload = json.dumps(
        {
            "articles": [
                {
                    "url": "/notice/admission",
                    "title": "关于2026年秋季幼儿园拟录取名单的公示",
                },
                {
                    "url": "/notice/result",
                    "title": "关于生物医药专项资金拟支持项目名单的公示",
                },
                {
                    "url": "/notice/general",
                    "title": "关于办公场所调整的公示",
                },
            ]
        },
        ensure_ascii=False,
    )
    rules = {
        "list_json_items": "articles",
        "list_json_url_field": "url",
        "list_json_title_field": "title",
        "detail_include_keywords": ["公示", "名单"],
        "detail_required_context_keywords": ["项目", "研发", "专项资金"],
        "detail_exclude_keywords": ["招生", "录取", "幼儿园", "中小学"],
        "max_items": 10,
    }

    assert extract_list_follow_items(
        payload,
        "https://gov.example/postmeta/notices.json",
        rules,
    ) == [
        {
            "url": "https://gov.example/notice/result",
            "title": "关于生物医药专项资金拟支持项目名单的公示",
        }
    ]


def test_extract_embedded_json_content_reads_article_from_inline_config() -> None:
    embedded_html = """
    <script>
      window._CONFIG = {
        question_data: {
          "article": {
            "title": "项目申报指南征求意见通知",
            "content": "<p>完整的项目申报正文</p>"
          }
        },
        answer_data: null
      };
    </script>
    """

    assert extract_embedded_json_content(
        embedded_html,
        assignment="question_data",
        content_path="article.content",
        title_path="article.title",
    ) == {
        "title": "项目申报指南征求意见通知",
        "content_html": "<p>完整的项目申报正文</p>",
    }


def test_parse_with_rules_extracts_published_at_text() -> None:
    html = """
    <html><body>
      <h1 class="article-title">关于组织申报重点专项的通知</h1>
      <div class="article-meta">发布时间：2026年07月21日 来源：科技部</div>
      <div class="article-body"><p>申报正文</p></div>
    </body></html>
    """

    parsed = parse_with_rules(
        html,
        {
            "title": "css:h1.article-title",
            "published_at": "css:.article-meta",
            "content": "css:.article-body",
        },
    )

    assert parsed["published_at"] == "发布时间：2026年07月21日 来源：科技部"


def test_strip_meta_for_detail_parse() -> None:
    rules = {
        "crawl_mode": "list_follow",
        "list_item": ".row",
        "detail_link": "a@href",
        "max_items": 5,
        "fields": {"x": "y"},
        "title": "css:h1",
        "content": "css:article",
    }
    stripped = strip_meta_for_detail_parse(rules)
    assert stripped == {"title": "css:h1", "content": "css:article"}


def test_resolve_list_page_urls_template_and_extra() -> None:
    rules = {
        "list_url_template": "https://ex.example/list?page={page}",
        "list_page_from": 2,
        "list_page_to": 4,
        "max_list_pages": 10,
        "list_page_urls": ["https://ex.example/other"],
    }
    urls = resolve_list_page_urls("https://ex.example/", rules)
    assert urls[0] == "https://ex.example/"
    assert "https://ex.example/other" in urls
    assert "https://ex.example/list?page=2" in urls
    assert "https://ex.example/list?page=4" in urls
    assert "https://ex.example/list?page=1" not in urls


def test_resolve_list_page_urls_max_list_pages() -> None:
    rules = {
        "list_url_template": "https://x.test/p/{page}",
        "list_page_from": 1,
        "list_page_to": 100,
        "max_list_pages": 3,
    }
    urls = resolve_list_page_urls("https://x.test/", rules)
    template_urls = [u for u in urls if "/p/" in u]
    assert len(template_urls) == 3


def test_resolve_list_page_urls_can_use_feed_without_public_page() -> None:
    rules = {
        "list_page_urls_only": True,
        "list_page_urls": ["https://gov.example/postmeta/notices.json"],
    }

    assert resolve_list_page_urls(
        "https://gov.example/notices/",
        rules,
    ) == ["https://gov.example/postmeta/notices.json"]


def test_extract_list_follow_urls_respects_url_cap() -> None:
    parts = [f"<div class='i'><a href='/p/{n}'>x</a></div>" for n in range(10)]
    html = "".join(parts)
    rules = {"list_item": ".i", "detail_link": "a@href", "max_items": 50}
    urls = extract_list_follow_urls(html, "https://z.example/", rules, url_cap=3)
    assert len(urls) == 3


def test_detail_rules_json_roundtrip_keys() -> None:
    rules = {
        "crawl_mode": "list_follow",
        "list_item": ".row",
        "detail_link": "a@href",
        "title": "css:h1",
        "content": "css:article",
    }
    j = detail_rules_json(rules)
    assert j is not None
    assert "list_item" not in j
    assert "title" in j


def test_detail_url_limit_invalid() -> None:
    assert detail_url_limit({"max_items": "x"}) == 20


def test_extract_next_list_page_url_relative() -> None:
    html = '<html><a class="n" href="/list/2">Next</a></html>'
    rules = {"list_next_page": "a.n@href", "same_host_only": True}
    nxt = extract_next_list_page_url(html, "https://ex.example/list/1", rules)
    assert nxt == "https://ex.example/list/2"


def test_extract_next_list_page_url_same_page_returns_none() -> None:
    html = '<html><a class="n" href="/list/1">Self</a></html>'
    rules = {"list_next_page": "a.n@href"}
    assert extract_next_list_page_url(html, "https://ex.example/list/1", rules) is None


def test_extract_next_list_page_off_host() -> None:
    html = '<html><a href="https://evil.example/x">x</a></html>'
    rules = {"list_next_page": "a@href", "same_host_only": True}
    assert extract_next_list_page_url(html, "https://ex.example/", rules) is None


def test_list_request_delay_seconds_capped() -> None:
    assert list_request_delay_seconds({"list_delay_ms": 999_999}) == 60.0
    assert list_request_delay_seconds({"list_delay_ms": 0}) == 0.0


def test_list_page_fetch_budget() -> None:
    assert list_page_fetch_budget({"max_list_pages": 999}) == 50


def test_detail_retry_policy_values() -> None:
    assert detail_retry_policy(None) == "all"
    assert detail_retry_policy({"detail_retry_policy": "transient"}) == "transient"
    assert detail_retry_policy({"retry_policy": "network"}) == "transient"
    assert detail_retry_policy({"detail_retry_policy": "ALL"}) == "all"


def test_should_retry_transient_httpx() -> None:
    req = httpx.Request("GET", "https://example.com/a")
    exc_503 = httpx.HTTPStatusError(
        "err",
        request=req,
        response=httpx.Response(503, request=req),
    )
    exc_404 = httpx.HTTPStatusError(
        "err",
        request=req,
        response=httpx.Response(404, request=req),
    )
    exc_429 = httpx.HTTPStatusError(
        "err",
        request=req,
        response=httpx.Response(429, request=req),
    )
    assert should_retry_detail_failure(exc_503, "transient") is True
    assert should_retry_detail_failure(exc_429, "transient") is True
    assert should_retry_detail_failure(exc_404, "transient") is False
    assert should_retry_detail_failure(exc_404, "all") is True
    assert should_retry_detail_failure(ValueError("x"), "transient") is False
    assert should_retry_detail_failure(ValueError("x"), "all") is True


def test_detail_retry_count_bounds() -> None:
    assert detail_retry_count(None) == 0
    assert detail_retry_count({"detail_retries": 0}) == 0
    assert detail_retry_count({"detail_retries": 2}) == 2
    assert detail_retry_count({"detail_retries": 99}) == 3


def test_detail_retry_sleep_seconds_capped() -> None:
    s = detail_retry_sleep_seconds({"detail_retry_backoff_ms": 100_000}, 3)
    assert s == 30.0


def test_detail_request_delay_seconds() -> None:
    assert detail_request_delay_seconds(None) == 0.0
    assert detail_request_delay_seconds({"detail_delay_ms": 1500}) == 1.5
    assert detail_request_delay_seconds({"detail_delay_ms": 999_999}) == 60.0


def test_fetch_timeout_seconds() -> None:
    assert fetch_timeout_seconds(None, 30.0) == 30.0
    assert fetch_timeout_seconds({"request_timeout_sec": 60}, 30.0) == 60.0
    assert fetch_timeout_seconds({"fetch_timeout_sec": 3}, 30.0) == 5.0
    assert fetch_timeout_seconds({"request_timeout_sec": 999}, 30.0) == 120.0


def test_fetch_http_cookies() -> None:
    assert fetch_http_cookies(None) is None
    jar = fetch_http_cookies({"http_cookies": {"sid": "abc", "n": 1}})
    assert jar == {"sid": "abc", "n": "1"}


def test_fetch_cookie_domain_override() -> None:
    assert fetch_cookie_domain_override(None) is None
    assert fetch_cookie_domain_override({"cookie_domain": " .ex.com "}) == ".ex.com"


def test_fetch_http_headers_user_agent_and_merge() -> None:
    h = fetch_http_headers(
        {
            "http_headers": {"Accept-Language": "zh-CN", "X-Foo": 1},
            "user_agent": "CustomBot/1.0",
        }
    )
    assert h is not None
    assert h["User-Agent"] == "CustomBot/1.0"
    assert h["Accept-Language"] == "zh-CN"
    assert h["X-Foo"] == "1"


def test_fetch_login_flow_basic_mapping() -> None:
    flow = fetch_login_flow(
        {
            "login_username": "alice",
            "login_password": "secret",
            "login_values": {"otp": "123456"},
            "login_session_key": "task:demo",
            "login_session_ttl_sec": 3600,
            "login_flow": {
                "url": "https://example.com/login",
                "success_selector": ".dashboard",
                "session_check_selector": ".nav-user",
                "session_check_url": "https://example.com/home",
                "steps": [
                    {"action": "fill", "selector": "#u", "value_from": "login_username"},
                    {"action": "fill", "selector": "#p", "value_from": "login_password"},
                    {"action": "fill", "selector": "#otp", "value_from": "otp"},
                    {"action": "click", "selector": "button[type=submit]"},
                    {"action": "wait_for_selector", "selector": ".dashboard"},
                ],
            },
        }
    )
    assert flow is not None
    assert flow["url"] == "https://example.com/login"
    assert flow["success_selector"] == ".dashboard"
    assert flow["session_key"] == "task:demo"
    assert flow["session_ttl_sec"] == 3600
    assert flow["session_check_selector"] == ".nav-user"
    assert flow["session_check_url"] == "https://example.com/home"
    assert isinstance(flow["steps"], list) and len(flow["steps"]) == 5
    values = flow["values"]
    assert isinstance(values, dict)
    assert values["login_username"] == "alice"
    assert values["login_password"] == "secret"
    assert values["otp"] == "123456"


def test_fetch_login_flow_invalid_returns_none() -> None:
    assert fetch_login_flow(None) is None
    assert fetch_login_flow({"login_flow": "x"}) is None
    assert fetch_login_flow({"login_flow": {"steps": []}}) is None


def test_anti_bot_defaults_and_customization() -> None:
    assert anti_bot_block_status_codes(None) == {403, 429}
    assert anti_bot_block_status_codes({"anti_bot_block_status_codes": [401, 403, "429"]}) == {
        401,
        403,
        429,
    }
    assert anti_bot_block_backoff_seconds({"anti_bot_block_backoff_ms": 1500}) == 1.5
    assert anti_bot_retry_on_block({"anti_bot_retry_on_block": False}) is False
    assert anti_bot_challenge_keywords({"anti_bot_challenge_keywords": ["captcha", "验证"]}) == [
        "captcha",
        "验证",
    ]


def test_looks_like_anti_bot_challenge() -> None:
    html = "<html><body>Please verify you are human</body></html>"
    assert looks_like_anti_bot_challenge(html, None) is True
    assert (
        looks_like_anti_bot_challenge(
            "<html>all good</html>",
            {"anti_bot_challenge_keywords": ["waf marker"]},
        )
        is False
    )
    assert (
        looks_like_anti_bot_challenge(
            """
            <html>
              <body>
                <div class="meeting-detail"><h1>2026 生物医药大会</h1></div>
                <script>const captchaLabel = "安全验证";</script>
              </body>
            </html>
            """,
            {
                "anti_bot_valid_selector": ".meeting-detail h1",
                "anti_bot_challenge_keywords": ["captcha", "安全验证"],
            },
        )
        is False
    )


def test_fetch_proxy_config() -> None:
    assert fetch_proxy_config(None) is None
    cfg = fetch_proxy_config(
        {
            "proxy_server": "http://127.0.0.1:8080",
            "proxy_username": "u",
            "proxy_password": "p",
            "proxy_on_block_only": "true",
            "proxy_failover_enabled": True,
        }
    )
    assert cfg is not None
    assert cfg["server"] == "http://127.0.0.1:8080"
    assert cfg["username"] == "u"
    assert cfg["password"] == "p"
    assert cfg["on_block_only"] is True
    assert cfg["failover_enabled"] is True


def test_strip_meta_strips_detail_policy_keys() -> None:
    rules = {
        "crawl_mode": "list_follow",
        "detail_retries": 2,
        "detail_delay_ms": 100,
        "detail_retry_backoff_ms": 500,
        "title": "css:h1",
    }
    assert strip_meta_for_detail_parse(rules) == {"title": "css:h1"}
    j = detail_rules_json(rules)
    assert j is not None
    assert "detail_retries" not in j


def test_strip_meta_strips_fetch_options() -> None:
    rules = {
        "request_timeout_sec": 45,
        "user_agent": "X",
        "http_headers": {"a": "b"},
        "detail_retry_policy": "transient",
        "http_cookies": {"s": "v"},
        "cookie_domain": ".ex.com",
        "title": "css:h1",
    }
    assert strip_meta_for_detail_parse(rules) == {"title": "css:h1"}
