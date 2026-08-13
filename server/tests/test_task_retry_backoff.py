from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import uuid

import app.engine.pipeline as pipeline_mod
import pytest
from fastapi.testclient import TestClient

from app.repositories.data_repo import DataRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskCreate, TaskRunPayload, TaskStatus
from app.services.dashboard_service import DashboardService
from app.services.task_service import TaskService


async def _instant_pipeline_run(_task_id: int) -> None:
    return


@pytest.mark.asyncio
async def test_catch_up_stale_tasks_defers_recent_failed_sources_in_backoff_window() -> None:
    fixed_now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    stale_tasks = [
        SimpleNamespace(
            id=11,
            name="科技部项目申报采集",
            last_run_status="failed",
            last_run_at=fixed_now - timedelta(minutes=20),
            last_success_at=fixed_now - timedelta(days=2),
            last_error_message="httpx.ReadTimeout: The read operation timed out",
        ),
        SimpleNamespace(
            id=12,
            name="长沙市科技局项目申报采集",
            last_run_status="failed",
            last_run_at=fixed_now - timedelta(hours=4),
            last_success_at=fixed_now - timedelta(days=3),
            last_error_message="httpx.ReadTimeout: The read operation timed out",
        ),
    ]

    class FakeTaskRepository:
        async def list_stale_enabled(self, *, stale_before):
            assert stale_before == fixed_now - timedelta(hours=24)
            return stale_tasks

    class FakeCrawlService:
        def __init__(self) -> None:
            self.calls: list[int] = []

        async def trigger_now(self, task_id: int) -> TaskRunPayload:
            self.calls.append(task_id)
            return TaskRunPayload(task_id=task_id, status="queued", recovered_stale_run=False)

    class FakeLogRepository:
        async def create(self, **_kwargs) -> None:
            return None

    crawl_service = FakeCrawlService()
    service = TaskService(
        task_repo=FakeTaskRepository(),  # type: ignore[arg-type]
        log_repo=FakeLogRepository(),  # type: ignore[arg-type]
        crawl_service=crawl_service,  # type: ignore[arg-type]
        scheduler=SimpleNamespace(),  # type: ignore[arg-type]
    )

    result = await service.catch_up_stale_tasks(now=fixed_now)

    assert crawl_service.calls == [12]
    assert result.queued_task_ids == [12]
    assert [item.task_id for item in result.deferred_tasks] == [11]
    assert result.deferred_tasks[0].failure_kind == "timeout"
    assert result.deferred_tasks[0].next_retry_at == fixed_now + timedelta(minutes=10)


def test_post_run_enabled_defers_recent_failed_task_with_retry_metadata(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
    test_database_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(pipeline_mod, "run_task", _instant_pipeline_run)
    client = asgi_test_client
    suffix = uuid.uuid4().hex[:10]
    created = client.post(
        "/v1/tasks",
        json={
            "name": f"pytest_backoff_{suffix}",
            "start_url": "https://example.com/backoff",
            "cron_expr": "0 0 * * *",
            "status": 1,
        },
        headers=auth_headers,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]

    recent_failed_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    with sqlite3.connect(test_database_path) as conn:
        conn.execute(
            """
            update tasks
               set last_run_status = ?,
                   last_run_at = ?,
                   last_success_at = ?,
                   last_error_message = ?
             where id = ?
            """,
            (
                "failed",
                recent_failed_at,
                None,
                "httpx.ReadTimeout: The read operation timed out",
                task_id,
            ),
        )
        conn.commit()

    r = client.post("/v1/tasks/run-enabled", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert task_id not in data["queued_task_ids"]
    assert data["deferred_tasks"][0]["task_id"] == task_id
    assert data["deferred_tasks"][0]["failure_kind"] == "timeout"
    assert data["deferred_tasks"][0]["next_retry_at"] is not None

    assert client.delete(f"/v1/tasks/{task_id}", headers=auth_headers).status_code == 200


@pytest.mark.asyncio
async def test_dashboard_reports_next_retry_for_recent_failed_source(async_session) -> None:
    task_repo = TaskRepository(async_session)
    data_repo = DataRepository(async_session)
    keyword_repo = KeywordRepository(async_session)
    now = datetime.now(timezone.utc)

    task = await task_repo.create(
        TaskCreate(
            name="湖南科技厅项目申报采集",
            start_url="https://kjt.hunan.gov.cn/root",
            parser_rules=None,
            cron_expr="0 8,14 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    task.last_run_status = "failed"
    task.last_run_at = now - timedelta(minutes=20)
    task.last_success_at = now - timedelta(days=3)
    task.last_error_message = "httpx.ReadTimeout: The read operation timed out"
    await async_session.commit()

    overview = await DashboardService(data_repo, task_repo, keyword_repo).get_overview()

    assert overview.collection_health.backoff_task_count == 1
    issue = overview.collection_health.issues[0]
    assert issue.task_id == task.id
    assert issue.failure_kind == "timeout"
    assert issue.backoff_active is True
    assert issue.next_retry_at is not None
    assert issue.next_retry_at > now
