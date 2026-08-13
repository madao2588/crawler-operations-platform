from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import app.core.lifecycle as lifecycle
from app.schemas.task import TaskRunPayload
from app.services.crawl_service import TaskRunConflictError
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_bootstrap_queues_stale_enabled_tasks_after_loading_schedules(monkeypatch) -> None:
    events: list[str] = []

    class SessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args) -> None:
            return None

    class FakeCrawlService:
        def __init__(self, **_kwargs) -> None:
            pass

        async def recover_stale_tasks(self) -> None:
            events.append("recover-active")

    class FakeTaskService:
        def __init__(self, **_kwargs) -> None:
            pass

        async def ensure_required_source_tasks(self) -> None:
            events.append("ensure")

        async def load_enabled_tasks(self) -> None:
            events.append("load")

        async def catch_up_stale_tasks(self) -> None:
            events.append("catch-up")

    monkeypatch.setattr(lifecycle, "AsyncSessionLocal", lambda: SessionContext())
    monkeypatch.setattr(lifecycle, "TaskRepository", lambda _session: object())
    monkeypatch.setattr(lifecycle, "LogRepository", lambda _session: object())
    monkeypatch.setattr(lifecycle, "CrawlService", FakeCrawlService)
    monkeypatch.setattr(lifecycle, "TaskService", FakeTaskService)
    monkeypatch.setattr(lifecycle.settings, "startup_catch_up_enabled", True)

    await lifecycle.bootstrap_tasks()

    assert events == ["ensure", "recover-active", "load", "catch-up"]


@pytest.mark.asyncio
async def test_catch_up_stale_tasks_queues_only_repository_candidates() -> None:
    fixed_now = datetime(2026, 8, 10, 2, 15, tzinfo=UTC)
    stale_tasks = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    class FakeTaskRepository:
        def __init__(self) -> None:
            self.stale_before = None

        async def list_stale_enabled(self, *, stale_before):
            self.stale_before = stale_before
            return stale_tasks

    class FakeCrawlService:
        def __init__(self) -> None:
            self.calls: list[int] = []

        async def trigger_now(self, task_id: int) -> TaskRunPayload:
            self.calls.append(task_id)
            if task_id == 2:
                raise TaskRunConflictError("already queued")
            return TaskRunPayload(task_id=task_id, status="queued", recovered_stale_run=False)

    class FakeLogRepository:
        def __init__(self) -> None:
            self.messages: list[str] = []

        async def create(self, **kwargs) -> None:
            self.messages.append(str(kwargs["message"]))

    task_repo = FakeTaskRepository()
    crawl_service = FakeCrawlService()
    log_repo = FakeLogRepository()
    service = TaskService(
        task_repo=task_repo,  # type: ignore[arg-type]
        log_repo=log_repo,  # type: ignore[arg-type]
        crawl_service=crawl_service,  # type: ignore[arg-type]
        scheduler=SimpleNamespace(),  # type: ignore[arg-type]
    )

    result = await service.catch_up_stale_tasks(now=fixed_now)

    assert task_repo.stale_before == fixed_now - timedelta(hours=24)
    assert crawl_service.calls == [1, 2]
    assert result.queued_task_ids == [1]
    assert result.skipped_task_ids == [2]
    assert log_repo.messages == ["startup catch-up: queued=1 skipped=1 deferred=0 errors=0"]
