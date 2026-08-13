import json

import httpx
import pytest

from scripts import check_requirement1_sources as healthcheck


def _list_follow_template() -> dict[str, str]:
    return {
        "id": "demo_source",
        "label": "Demo source",
        "start_url": "https://gov.example/notices",
        "parser_rules": json.dumps(
            {
                "crawl_mode": "list_follow",
                "list_item": ".list li",
                "detail_link": "a@href",
                "detail_include_keywords": ["notice"],
                "max_items": 10,
                "title": "css:h1",
                "published_at": "css:.meta",
                "content": "css:.body",
            }
        ),
    }


@pytest.mark.asyncio
async def test_probe_source_reports_list_detail_and_published_at(monkeypatch) -> None:
    template = _list_follow_template()

    async def fake_fetch(url: str, _rules: dict[str, object]) -> tuple[str, str]:
        if url.endswith("/notices"):
            return (
                '<ul class="list"><li><a href="/notices/1">Project notice</a></li></ul>',
                "static",
            )
        return (
            "<h1>Project notice</h1>"
            "<div class='meta'>Published at: 2026-07-24</div>"
            "<div class='body'><p>Body text for the requirement 1 source.</p></div>",
            "static",
        )

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["status"] == "ok"
    assert result["matched_items"] == 1
    assert result["detail_title"] == "Project notice"
    assert result["published_at"] == "2026-07-23T16:00:00+00:00"


@pytest.mark.asyncio
async def test_probe_source_reports_both_requirement_1_information_types(monkeypatch) -> None:
    template = _list_follow_template()

    async def fake_fetch(url: str, _rules: dict[str, object]) -> tuple[str, str]:
        if url.endswith("/notices"):
            return (
                '<ul class="list">'
                '<li><a href="/notices/apply">2026年度科技项目申报通知</a></li>'
                '<li><a href="/notices/result">2026年度拟立项项目公示</a></li>'
                '</ul>',
                "static",
            )
        return (
            "<h1>2026年度科技项目申报通知</h1>"
            "<div class='meta'>Published at: 2026-07-24</div>"
            "<div class='body'><p>Project notice body.</p></div>",
            "static",
        )

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["signal_counts"] == {
        "申报通知": 1,
        "结果公示": 1,
        "其他项目线索": 0,
    }
    assert result["signal_samples"]["申报通知"] == ["2026年度科技项目申报通知"]
    assert result["signal_samples"]["结果公示"] == ["2026年度拟立项项目公示"]


@pytest.mark.asyncio
async def test_probe_source_marks_missing_result_publications_as_incomplete(monkeypatch) -> None:
    template = _list_follow_template()
    template["id"] = "most_project_declaration"

    async def fake_fetch(url: str, _rules: dict[str, object]) -> tuple[str, str]:
        if url.endswith("/notices"):
            return (
                '<ul class="list">'
                '<li><a href="/notices/apply">2026年度科技项目申报通知</a></li>'
                '<li><a href="/notices/apply-2">关于组织申报的补充说明</a></li>'
                "</ul>",
                "static",
            )
        return (
            "<h1>2026年度科技项目申报通知</h1>"
            "<div class='meta'>Published at: 2026-07-24</div>"
            "<div class='body'><p>Project notice body.</p></div>",
            "static",
        )

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["status"] == "degraded"
    assert result["failure_kind"] == "incomplete_requirement_coverage"
    assert result["missing_signals"] == ["结果公示"]


@pytest.mark.asyncio
async def test_probe_source_uses_official_reference_to_verify_unobserved_signal(
    monkeypatch,
) -> None:
    template = _list_follow_template()
    template["id"] = "most_project_declaration"
    reference_url = "https://gov.example/notices/historical-result"
    monkeypatch.setattr(
        healthcheck,
        "PROJECT_SIGNAL_CAPABILITY_EVIDENCE",
        {
            "most_project_declaration": {
                "结果公示": {
                    "url": reference_url,
                    "title": "关于重点专项2021年度拟立项项目安排公示的通知",
                }
            }
        },
    )

    async def fake_fetch(url: str, _rules: dict[str, object]) -> tuple[str, str]:
        if url.endswith("/notices"):
            return (
                '<ul class="list">'
                '<li><a href="/notices/apply">2026年度科技项目申报通知</a></li>'
                "</ul>",
                "static",
            )
        if url == reference_url:
            return (
                "<h1>关于重点专项2021年度拟立项项目安排公示的通知</h1>"
                "<div class='meta'>发布时间：2021年12月09日</div>"
                "<div class='body'><p>现将拟立项项目信息进行公示。</p></div>",
                "static",
            )
        return (
            "<h1>2026年度科技项目申报通知</h1>"
            "<div class='meta'>发布时间：2026年07月24日</div>"
            "<div class='body'><p>项目申报正文。</p></div>",
            "static",
        )

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["status"] == "ok"
    assert result["signal_counts"]["结果公示"] == 0
    assert result["unobserved_signals"] == ["结果公示"]
    assert result["missing_signals"] == []
    assert result["verified_signal_evidence"]["结果公示"] == {
        "url": reference_url,
        "title": "关于重点专项2021年度拟立项项目安排公示的通知",
        "published_at": "2021-12-08T16:00:00+00:00",
        "content_length": len("现将拟立项项目信息进行公示。"),
        "fetch_mode": "static",
    }


@pytest.mark.asyncio
async def test_probe_source_reports_preferred_list_title(monkeypatch) -> None:
    template = _list_follow_template()
    rules = json.loads(template["parser_rules"])
    rules["prefer_list_title"] = True
    template["parser_rules"] = json.dumps(rules)

    async def fake_fetch(url: str, _rules: dict[str, object]) -> tuple[str, str]:
        if url.endswith("/notices"):
            return (
                '<ul class="list"><li><a href="/notices/1">Useful project notice</a></li></ul>',
                "static",
            )
        return (
            "<h1>Generic author name</h1>"
            "<div class='meta'>Published at: 2026-07-24</div>"
            "<div class='body'><p>Body text for the requirement 1 source.</p></div>",
            "static",
        )

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["detail_title"] == "Useful project notice"


@pytest.mark.asyncio
async def test_probe_source_hydrates_embedded_json_content(monkeypatch) -> None:
    template = _list_follow_template()
    rules = json.loads(template["parser_rules"])
    rules.update(
        {
            "embedded_content_url": "iframe.notice@src",
            "embedded_content_json_assignment": "question_data",
            "embedded_content_json_path": "article.content",
            "embedded_content_title_path": "article.title",
        }
    )
    template["parser_rules"] = json.dumps(rules)

    async def fake_fetch(url: str, _rules: dict[str, object]) -> tuple[str, str]:
        if url.endswith("/notices"):
            return (
                '<ul class="list"><li><a href="/notices/1">Project notice</a></li></ul>',
                "static",
            )
        if url.endswith("/notices/1"):
            return (
                "<h1>Project notice</h1>"
                "<div class='meta'>Published at: 2026-07-24</div>"
                "<div class='body'><iframe class='notice' src='/embedded/1'></iframe></div>",
                "static",
            )
        return (
            '<script>window.C={question_data:{"article":{"title":"Project notice",'
            '"content":"<p>Complete embedded project notice content.</p>"}}};</script>',
            "static",
        )

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["status"] == "ok"
    assert result["content_length"] == len("Complete embedded project notice content.")


@pytest.mark.asyncio
async def test_fetch_preserves_static_and_dynamic_fallback_errors(monkeypatch) -> None:
    request = httpx.Request("GET", "https://gov.example/notices")
    static_exc = httpx.HTTPStatusError(
        "403 forbidden",
        request=request,
        response=httpx.Response(403, request=request),
    )
    dynamic_exc = httpx.ReadTimeout("dynamic timed out", request=request)

    async def fake_fetch_static(*_args, **_kwargs) -> str:
        raise static_exc

    async def fake_fetch_dynamic(*_args, **_kwargs) -> str:
        raise dynamic_exc

    monkeypatch.setattr(healthcheck, "fetch_static", fake_fetch_static)
    monkeypatch.setattr(healthcheck, "fetch_dynamic", fake_fetch_dynamic)

    with pytest.raises(Exception) as exc_info:
        await healthcheck._fetch("https://gov.example/notices", {})

    message = str(exc_info.value)
    assert "403" in message
    assert "dynamic timed out" in message


@pytest.mark.asyncio
async def test_probe_source_classifies_network_failures(monkeypatch) -> None:
    template = _list_follow_template()

    async def fake_fetch(
        url: str,
        _rules: dict[str, object],
    ) -> tuple[str, str]:
        request = httpx.Request("GET", url)
        raise httpx.ConnectError("TLS connection closed", request=request)

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["status"] == "failed"
    assert result["failure_kind"] == "network_unreachable"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (403, "http_403"),
        (429, "http_429"),
    ],
)
def test_classify_failure_distinguishes_http_block_statuses(
    status_code: int,
    expected: str,
) -> None:
    request = httpx.Request("GET", "https://gov.example/notices")
    exc = httpx.HTTPStatusError(
        f"status code {status_code}",
        request=request,
        response=httpx.Response(status_code, request=request),
    )

    assert healthcheck._classify_failure(exc, []) == expected


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (
            httpx.ReadTimeout(
                "request timed out",
                request=httpx.Request("GET", "https://gov.example/notices"),
            ),
            "timeout",
        ),
        (
            httpx.ConnectError(
                "network is unreachable",
                request=httpx.Request("GET", "https://gov.example/notices"),
            ),
            "network_unreachable",
        ),
    ],
)
def test_classify_failure_distinguishes_timeout_and_network_unreachable(
    exc: Exception,
    expected: str,
) -> None:
    assert healthcheck._classify_failure(exc, []) == expected


@pytest.mark.asyncio
async def test_probe_source_classifies_zero_detail_links_as_parse_drift(monkeypatch) -> None:
    template = _list_follow_template()

    async def fake_fetch(url: str, _rules: dict[str, object]) -> tuple[str, str]:
        _ = url
        return "<html><body><div>No matching links</div></body></html>", "static"

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["status"] == "failed"
    assert result["failure_kind"] == "parse_drift"


@pytest.mark.asyncio
async def test_probe_source_classifies_missing_detail_fields_as_parse_drift(monkeypatch) -> None:
    template = _list_follow_template()

    async def fake_fetch(url: str, _rules: dict[str, object]) -> tuple[str, str]:
        if url.endswith("/notices"):
            return (
                '<ul class="list"><li><a href="/notices/1">Project notice</a></li></ul>',
                "static",
            )
        return (
            "<h1></h1>"
            "<div class='meta'></div>"
            "<div class='body'><p></p></div>",
            "dynamic",
        )

    monkeypatch.setattr(healthcheck, "_fetch", fake_fetch)

    result = await healthcheck.probe_source(template)

    assert result["status"] == "degraded"
    assert result["failure_kind"] == "parse_drift"
