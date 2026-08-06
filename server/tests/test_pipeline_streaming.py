import json

import pytest

import app.engine.pipeline as pipeline_mod


class _DummyTask:
    def __init__(self) -> None:
        self.id = 1
        self.start_url = "https://example.com/list-1"
        self.parser_rules = json.dumps(
            {
                "crawl_mode": "list_follow",
                "list_item": ".item",
                "detail_link": "a@href",
                "max_items": 2,
                "list_page_urls": ["https://example.com/list-2"],
            }
        )


class _FakeTaskRepo:
    def __init__(self, _session) -> None:
        self.task = _DummyTask()

    async def get_by_id(self, task_id: int):
        if task_id != 1:
            return None
        return self.task


class _SingleTaskRepo:
    def __init__(self, _session) -> None:
        self.task = type(
            "SingleTask",
            (),
            {
                "id": 1,
                "start_url": "https://example.com/single",
                "parser_rules": None,
            },
        )()

    async def get_by_id(self, task_id: int):
        if task_id != 1:
            return None
        return self.task


class _FakeDataRepo:
    def __init__(self, _session) -> None:
        pass


class _FakeLogRepo:
    captured_messages: list[str] = []

    def __init__(self, _session) -> None:
        self.messages: list[str] = []

    async def create(self, **kwargs) -> None:
        message = kwargs.get("message")
        if isinstance(message, str):
            self.messages.append(message)
            _FakeLogRepo.captured_messages.append(message)


class _FakeSessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


@pytest.mark.asyncio
async def test_list_follow_streams_details_while_scanning_lists(monkeypatch) -> None:
    events: list[str] = []
    _FakeLogRepo.captured_messages.clear()

    monkeypatch.setattr(pipeline_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())
    monkeypatch.setattr(pipeline_mod, "TaskRepository", _FakeTaskRepo)
    monkeypatch.setattr(pipeline_mod, "DataRepository", _FakeDataRepo)
    monkeypatch.setattr(pipeline_mod, "LogRepository", _FakeLogRepo)

    async def fake_download_page(**kwargs) -> str:
        list_url = kwargs["url"]
        events.append(f"list:{list_url}")
        return list_url

    def fake_extract_list_follow_items(html: str, base_url: str, rules, *, url_cap=None):
        _ = (rules, url_cap)
        if html.endswith("list-1"):
            return [{"url": "https://example.com/detail-1", "title": "Detail 1"}]
        if html.endswith("list-2"):
            return [{"url": "https://example.com/detail-2", "title": "Detail 2"}]
        return []

    async def fake_collect_and_store_one_retrying(**kwargs) -> str:
        events.append(f"detail:{kwargs['page_url']}:{kwargs['fallback_title']}")
        return "stored"

    monkeypatch.setattr(pipeline_mod, "_download_page", fake_download_page)
    monkeypatch.setattr(pipeline_mod, "extract_list_follow_items", fake_extract_list_follow_items)
    monkeypatch.setattr(
        pipeline_mod,
        "_collect_and_store_one_retrying",
        fake_collect_and_store_one_retrying,
    )

    await pipeline_mod.run_task(1)

    assert events == [
        "list:https://example.com/list-1",
        "detail:https://example.com/detail-1:Detail 1",
        "list:https://example.com/list-2",
        "detail:https://example.com/detail-2:Detail 2",
    ]
    assert any("列表跟进运行摘要：" in msg and "入库 2" in msg for msg in _FakeLogRepo.captured_messages)


@pytest.mark.asyncio
async def test_single_page_emits_summary_log(monkeypatch) -> None:
    _FakeLogRepo.captured_messages.clear()

    monkeypatch.setattr(pipeline_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())
    monkeypatch.setattr(pipeline_mod, "TaskRepository", _SingleTaskRepo)
    monkeypatch.setattr(pipeline_mod, "DataRepository", _FakeDataRepo)
    monkeypatch.setattr(pipeline_mod, "LogRepository", _FakeLogRepo)

    async def fake_collect_and_store_one_retrying(**kwargs) -> str:
        _ = kwargs
        return "skipped_hash"

    monkeypatch.setattr(
        pipeline_mod,
        "_collect_and_store_one_retrying",
        fake_collect_and_store_one_retrying,
    )

    await pipeline_mod.run_task(1)

    assert any(
        "单页运行摘要：" in msg and "处理 1" in msg and "重复跳过 1" in msg for msg in _FakeLogRepo.captured_messages
    )


@pytest.mark.asyncio
async def test_list_follow_returns_partial_when_some_details_fail(monkeypatch) -> None:
    _FakeLogRepo.captured_messages.clear()

    monkeypatch.setattr(pipeline_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())
    monkeypatch.setattr(pipeline_mod, "TaskRepository", _FakeTaskRepo)
    monkeypatch.setattr(pipeline_mod, "DataRepository", _FakeDataRepo)
    monkeypatch.setattr(pipeline_mod, "LogRepository", _FakeLogRepo)

    async def fake_download_page(**kwargs) -> str:
        return kwargs["url"]

    def fake_extract_list_follow_items(html: str, base_url: str, rules, *, url_cap=None):
        _ = (html, base_url, rules, url_cap)
        return [
            {"url": "https://example.com/detail-ok", "title": "Detail OK"},
            {"url": "https://example.com/detail-failed", "title": "Detail Failed"},
        ]

    async def fake_collect_and_store_one_retrying(**kwargs) -> str:
        if kwargs["page_url"].endswith("detail-failed"):
            raise RuntimeError("detail rejected")
        return "stored"

    monkeypatch.setattr(pipeline_mod, "_download_page", fake_download_page)
    monkeypatch.setattr(pipeline_mod, "extract_list_follow_items", fake_extract_list_follow_items)
    monkeypatch.setattr(
        pipeline_mod,
        "_collect_and_store_one_retrying",
        fake_collect_and_store_one_retrying,
    )

    outcome = await pipeline_mod.run_task(1)

    assert outcome == "partial"
    assert any(
        "列表跟进运行摘要：" in msg and "入库 1" in msg and "失败 1" in msg
        for msg in _FakeLogRepo.captured_messages
    )
