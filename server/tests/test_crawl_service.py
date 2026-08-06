from types import SimpleNamespace

import pytest

import app.services.crawl_service as crawl_service_mod
from app.services.crawl_service import CrawlService


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

    async def create(self, **kwargs) -> None:
        self.rows.append(kwargs)


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
        "Run completed with partial failures; inspect the latest run summary."
    )
