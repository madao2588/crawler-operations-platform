import json

import pytest

from app.engine import test_pipeline


@pytest.mark.asyncio
async def test_test_run_list_follow_probes_list_then_one_detail(monkeypatch) -> None:
    list_url = "https://gov.example/notices"
    detail_url = "https://gov.example/notices/1"

    async def fake_fetch_static(url: str, **_kwargs) -> str:
        if url == list_url:
            return """
            <ul class="news_list">
              <li><a href="/notices/1">关于组织申报重点专项的通知</a></li>
            </ul>
            """
        if url == detail_url:
            return """
            <h1 class="title">关于组织申报重点专项的通知</h1>
            <div class="meta">发布时间：2026-07-24</div>
            <div class="body"><p>这是足够长的项目申报正文，用于验证列表跟随在线测试。</p></div>
            """
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(test_pipeline, "fetch_static", fake_fetch_static)
    rules = json.dumps(
        {
            "crawl_mode": "list_follow",
            "list_item": ".news_list li",
            "detail_link": "a@href",
            "detail_include_keywords": ["申报"],
            "max_items": 10,
            "title": "css:h1.title",
            "published_at": "css:.meta",
            "content": "css:.body",
        },
        ensure_ascii=False,
    )

    result = await test_pipeline.test_run(list_url, rules)

    assert result["error"] is None
    assert result["title"] == "关于组织申报重点专项的通知"
    assert "项目申报正文" in result["content_text"]
    assert any("列表命中 1 条" in note for note in result["trace"]["notes"])
