import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.services.crawl_service as crawl_service_mod
from app.services.crawl_service import CrawlService


@pytest.mark.asyncio
async def test_dispatch_limits_concurrent_collection_runs(monkeypatch) -> None:
    active = 0
    max_active = 0

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args) -> None:
            return None

    class FakeCrawlService:
        def __init__(self, **_kwargs) -> None:
            pass

        async def run_task(self, _task_id: int) -> None:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1

    monkeypatch.setattr(crawl_service_mod, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(crawl_service_mod, "TaskRepository", lambda _session: object())
    monkeypatch.setattr(crawl_service_mod, "LogRepository", lambda _session: object())
    monkeypatch.setattr(crawl_service_mod, "CrawlService", FakeCrawlService)

    await asyncio.gather(*(crawl_service_mod.dispatch_task_run(task_id) for task_id in range(5)))

    assert max_active == 2


class _TaskRepo:
    def __init__(self) -> None:
        self.task = SimpleNamespace(
            id=7,
            last_run_status=None,
            last_run_at=None,
            last_success_at=None,
            last_error_message=None,
        )
        self.updates: list[dict[str, object]] = []

    async def get_by_id(self, task_id: int):
        return self.task if task_id == self.task.id else None

    async def try_mark_running(self, task_id: int, *, run_at) -> bool:
        _ = (task_id, run_at)
        return True

    async def try_promote_queued_to_running(self, task_id: int, *, run_at) -> bool:
        _ = (task_id, run_at)
        return False

    async def list_stale_active(self, *, stale_before):
        _ = stale_before
        return []

    async def update_run_state(self, task, **kwargs):
        self.updates.append(kwargs)
        for key, value in kwargs.items():
            setattr(task, key, value)
        return task


class _LogRepo:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.latest_summary = SimpleNamespace(
            run_summary=(
                '{"kind":"run_summary","run_id":"abc123","mode":"list_follow",'
                '"metrics":{"detail_processed":5,"failed":2}}'
            ),
        )
        self.latest_error = SimpleNamespace(
            message="[run=abc123] Failed detail https://example.test/notice/5",
            error_stack="httpx.ReadTimeout: The read operation timed out",
        )

    async def create(self, **kwargs) -> None:
        self.rows.append(kwargs)

    async def get_latest_run_summary(self, *, task_id: int, created_after: datetime):
        assert task_id == 7
        assert created_after.tzinfo == timezone.utc
        return self.latest_summary

    async def get_latest_error(self, *, task_id: int, run_id: str, created_after: datetime):
        assert task_id == 7
        assert run_id == "abc123"
        assert created_after.tzinfo == timezone.utc
        return self.latest_error


@pytest.mark.asyncio
async def test_run_task_persists_partial_pipeline_result(monkeypatch) -> None:
    task_repo = _TaskRepo()
    log_repo = _LogRepo()
    service = CrawlService(task_repo=task_repo, log_repo=log_repo)

    async def partial_pipeline(task_id: int) -> str:
        assert task_id == 7
        return "partial"

    monkeypatch.setattr(
        crawl_service_mod,
        "import_module",
        lambda _name: SimpleNamespace(run_task=partial_pipeline),
    )

    await service.run_task(7)

    assert task_repo.task.last_run_status == "partial"
    assert task_repo.task.last_success_at is not None
    assert task_repo.task.last_error_message == (
        "列表跟进本次有 2 条处理失败；最近原因：请求超时。已成功采集的内容已保存。"
    )
