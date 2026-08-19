from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.data import CollectedData
from app.models.log import LogEntry
from app.models.task import Task
from app.repositories.log_repo import LogRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskStatus
from app.services.crawl_service import CrawlService
from app.services.task_service import DEMO_TASK_START_URLS, TaskService
from app.services.template_service import NEW_DRUG_SOURCE_TEMPLATES


@pytest.mark.asyncio
async def test_try_mark_running_second_claim_fails(async_session) -> None:
    async_session.add(
        Task(
            name="claim test",
            start_url="https://claim.example",
            cron_expr="0 * * * *",
            status=int(TaskStatus.ENABLED),
            last_run_status="queued",
        )
    )
    await async_session.commit()
    t = (await async_session.execute(select(Task).limit(1))).scalar_one()
    repo = TaskRepository(async_session)
    now = datetime.now(UTC)
    assert await repo.try_mark_running(t.id, run_at=now) is True
    assert await repo.try_mark_running(t.id, run_at=now) is False


@pytest.mark.asyncio
async def test_try_promote_queued_to_running(async_session) -> None:
    async_session.add(
        Task(
            name="promote test",
            start_url="https://promote.example",
            cron_expr="0 * * * *",
            status=int(TaskStatus.ENABLED),
            last_run_status="queued",
        )
    )
    await async_session.commit()
    t = (await async_session.execute(select(Task).limit(1))).scalar_one()
    repo = TaskRepository(async_session)
    now = datetime.now(UTC)
    assert await repo.try_promote_queued_to_running(t.id, run_at=now) is True
    t2 = await repo.get_by_id(t.id)
    assert t2 is not None
    assert t2.last_run_status == "running"
    assert await repo.try_promote_queued_to_running(t.id, run_at=now) is False


@pytest.mark.asyncio
async def test_try_mark_run_queued_false_when_already_queued(async_session) -> None:
    async_session.add(
        Task(
            name="queue test",
            start_url="https://queue.example",
            cron_expr="0 * * * *",
            status=int(TaskStatus.ENABLED),
            last_run_status="queued",
        )
    )
    await async_session.commit()
    t = (await async_session.execute(select(Task).limit(1))).scalar_one()
    repo = TaskRepository(async_session)
    now = datetime.now(UTC)
    assert await repo.try_mark_run_queued(t.id, run_at=now) is False


@pytest.mark.asyncio
async def test_list_stale_active_returns_old_running_and_queued(async_session) -> None:
    cutoff = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    async_session.add_all(
        [
            Task(
                name="Stale running",
                start_url="https://stale-running.example",
                cron_expr="0 * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="running",
                last_run_at=cutoff - timedelta(minutes=1),
            ),
            Task(
                name="Stale queued",
                start_url="https://stale-queued.example",
                cron_expr="0 * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="queued",
                last_run_at=cutoff - timedelta(minutes=5),
            ),
            Task(
                name="Fresh running",
                start_url="https://fresh-running.example",
                cron_expr="0 * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="running",
                last_run_at=cutoff + timedelta(minutes=1),
            ),
        ]
    )
    await async_session.commit()

    repo = TaskRepository(async_session)
    items = await repo.list_stale_active(stale_before=cutoff)
    assert [task.name for task in items] == ["Stale running", "Stale queued"]


@pytest.mark.asyncio
async def test_list_paginated_search_name(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="Alpha crawl",
                start_url="https://a.example",
                cron_expr="0 * * * *",
                status=int(TaskStatus.ENABLED),
            ),
            Task(
                name="Beta",
                start_url="https://b.example",
                cron_expr="0 * * * *",
                status=int(TaskStatus.ENABLED),
            ),
        ]
    )
    await async_session.commit()

    repo = TaskRepository(async_session)
    items, total = await repo.list_paginated(page=1, page_size=20, search="alpha")
    assert total == 1
    assert len(items) == 1
    assert items[0].name == "Alpha crawl"


@pytest.mark.asyncio
async def test_list_paginated_enabled_filter(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="On",
                start_url="https://on.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.ENABLED),
            ),
            Task(
                name="Off",
                start_url="https://off.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.DISABLED),
            ),
        ]
    )
    await async_session.commit()

    repo = TaskRepository(async_session)
    _, total_enabled = await repo.list_paginated(page=1, page_size=20, enabled="enabled")
    _, total_disabled = await repo.list_paginated(page=1, page_size=20, enabled="disabled")
    assert total_enabled == 1
    assert total_disabled == 1


@pytest.mark.asyncio
async def test_list_paginated_last_run_active(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="Running",
                start_url="https://r.example",
                cron_expr="* * * * *",
                status=1,
                last_run_status="running",
            ),
            Task(
                name="Done",
                start_url="https://d.example",
                cron_expr="* * * * *",
                status=1,
                last_run_status="success",
            ),
        ]
    )
    await async_session.commit()

    repo = TaskRepository(async_session)
    items, total = await repo.list_paginated(page=1, page_size=20, last_run="active")
    assert total == 1
    assert items[0].name == "Running"


@pytest.mark.asyncio
async def test_list_paginated_last_run_partial(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="Partial",
                start_url="https://partial.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="partial",
            ),
            Task(
                name="Success",
                start_url="https://success.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="success",
            ),
        ]
    )
    await async_session.commit()

    repo = TaskRepository(async_session)
    items, total = await repo.list_paginated(page=1, page_size=20, last_run="partial")

    assert total == 1
    assert [item.name for item in items] == ["Partial"]


@pytest.mark.asyncio
async def test_quarantine_failed_enabled_disables_failed_tasks(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="Failed source",
                start_url="https://failed.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="failed",
            ),
            Task(
                name="Healthy source",
                start_url="https://healthy.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="success",
            ),
            Task(
                name="Already disabled",
                start_url="https://disabled.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.DISABLED),
                last_run_status="failed",
            ),
        ]
    )
    await async_session.commit()

    repo = TaskRepository(async_session)
    quarantined = await repo.quarantine_failed_enabled()

    assert [task.name for task in quarantined] == ["Failed source"]
    failed = await repo.get_by_id(quarantined[0].id)
    assert failed is not None
    assert failed.status == int(TaskStatus.DISABLED)


@pytest.mark.asyncio
async def test_list_retryable_enabled_includes_partial_and_excludes_healthy_disabled_tasks(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="Retry this source",
                start_url="https://retry.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="failed",
            ),
            Task(
                name="Retry partially completed source",
                start_url="https://partial.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="partial",
            ),
            Task(
                name="Healthy source",
                start_url="https://healthy-retry.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.ENABLED),
                last_run_status="success",
            ),
            Task(
                name="Disabled failure",
                start_url="https://disabled-retry.example",
                cron_expr="* * * * *",
                status=int(TaskStatus.DISABLED),
                last_run_status="failed",
            ),
        ]
    )
    await async_session.commit()

    items = await TaskRepository(async_session).list_retryable_enabled()

    assert [task.name for task in items] == [
        "Retry this source",
        "Retry partially completed source",
    ]


@pytest.mark.asyncio
async def test_list_paginated_sort_last_run_at_desc_nulls_last(async_session) -> None:
    base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    async_session.add_all(
        [
            Task(
                name="WithTime",
                start_url="https://t.example",
                cron_expr="* * * * *",
                status=1,
                last_run_at=base,
            ),
            Task(
                name="NoTime",
                start_url="https://n.example",
                cron_expr="* * * * *",
                status=1,
                last_run_at=None,
            ),
        ]
    )
    await async_session.commit()

    repo = TaskRepository(async_session)
    items, _ = await repo.list_paginated(
        page=1,
        page_size=10,
        sort_by="last_run_at",
        sort_dir="desc",
    )
    assert [t.name for t in items] == ["WithTime", "NoTime"]


@pytest.mark.asyncio
async def test_list_paginated_sort_last_run_at_asc_nulls_first(async_session) -> None:
    base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    async_session.add_all(
        [
            Task(
                name="WithTime",
                start_url="https://t.example",
                cron_expr="* * * * *",
                status=1,
                last_run_at=base + timedelta(days=1),
            ),
            Task(
                name="NoTime",
                start_url="https://n.example",
                cron_expr="* * * * *",
                status=1,
                last_run_at=None,
            ),
        ]
    )
    await async_session.commit()

    repo = TaskRepository(async_session)
    items, _ = await repo.list_paginated(
        page=1,
        page_size=10,
        sort_by="last_run_at",
        sort_dir="asc",
    )
    assert [t.name for t in items] == ["NoTime", "WithTime"]


@pytest.mark.asyncio
async def test_ensure_required_source_tasks_replaces_demo_tasks(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="测试1（豆瓣）",
                start_url="https://movie.douban.com/top250",
                cron_expr="0 */6 * * *",
                status=int(TaskStatus.ENABLED),
            ),
            Task(
                name="Custom keep",
                start_url="https://custom.example/source",
                cron_expr="0 1 * * *",
                status=int(TaskStatus.DISABLED),
            ),
        ]
    )
    await async_session.commit()

    task_repo = TaskRepository(async_session)
    log_repo = LogRepository(async_session)
    service = TaskService(
        task_repo=task_repo,
        log_repo=log_repo,
        crawl_service=CrawlService(task_repo=task_repo, log_repo=log_repo),
    )

    await service.ensure_required_source_tasks()
    items, total = await task_repo.list_paginated(page=1, page_size=100, sort_by="id", sort_dir="asc")
    names = {task.name for task in items}
    urls = {task.start_url for task in items}

    assert total == len(NEW_DRUG_SOURCE_TEMPLATES) + 1
    assert "Custom keep" in names
    assert not (urls & DEMO_TASK_START_URLS)
    for source in NEW_DRUG_SOURCE_TEMPLATES:
        assert source["name"] in names


@pytest.mark.asyncio
async def test_ensure_required_source_tasks_renames_unique_source_without_duplication(
    async_session,
) -> None:
    canonical = next(
        source
        for source in NEW_DRUG_SOURCE_TEMPLATES
        if source["id"] == "most_project_declaration"
    )
    async_session.add(
        Task(
            name="科技部项目申报通知采集",
            start_url=str(canonical["start_url"]),
            cron_expr="0 7 * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.commit()

    task_repo = TaskRepository(async_session)
    log_repo = LogRepository(async_session)
    service = TaskService(
        task_repo=task_repo,
        log_repo=log_repo,
        crawl_service=CrawlService(task_repo=task_repo, log_repo=log_repo),
    )

    await service.ensure_required_source_tasks()
    items = await task_repo.list_all()
    matching = [
        task for task in items if task.start_url == canonical["start_url"]
    ]

    assert len(items) == len(NEW_DRUG_SOURCE_TEMPLATES)
    assert len(matching) == 1
    assert matching[0].name == canonical["name"]


@pytest.mark.asyncio
async def test_ensure_required_source_tasks_removes_demo_variants_and_canonical_duplicates(
    async_session,
) -> None:
    canonical = next(
        source
        for source in NEW_DRUG_SOURCE_TEMPLATES
        if source["id"] == "pubmed_literature"
    )
    retained_task = Task(
        name=str(canonical["name"]),
        start_url=str(canonical["start_url"]),
        cron_expr="0 1 * * *",
        status=int(TaskStatus.DISABLED),
    )
    duplicate_task = Task(
        name=str(canonical["name"]),
        start_url=str(canonical["start_url"]),
        cron_expr="0 2 * * *",
        status=int(TaskStatus.ENABLED),
    )
    async_session.add_all(
        [
            retained_task,
            duplicate_task,
            Task(
                name="News Monitor",
                start_url="https://example.com/news",
                cron_expr="0 */6 * * *",
                status=int(TaskStatus.ENABLED),
            ),
            Task(
                name="Tender Notice Monitor",
                start_url="https://example.com/tenders",
                cron_expr="0 */6 * * *",
                status=int(TaskStatus.ENABLED),
            ),
            Task(
                name="Portal Announcement Monitor",
                start_url="https://example.com/announcements",
                cron_expr="0 */6 * * *",
                status=int(TaskStatus.ENABLED),
            ),
        ]
    )
    await async_session.flush()
    async_session.add_all(
        [
            CollectedData(
                task_id=duplicate_task.id,
                title="重复任务已经采集的公告",
                content_text="应归并到保留任务",
                source_url="https://pubmed.ncbi.nlm.nih.gov/duplicate-history",
                content_hash="duplicate-task-history",
                category="竞品信息",
                quality_score=80,
            ),
            LogEntry(
                task_id=duplicate_task.id,
                level="INFO",
                message="duplicate task history",
            ),
        ]
    )
    await async_session.commit()

    task_repo = TaskRepository(async_session)
    log_repo = LogRepository(async_session)
    service = TaskService(
        task_repo=task_repo,
        log_repo=log_repo,
        crawl_service=CrawlService(task_repo=task_repo, log_repo=log_repo),
    )

    await service.ensure_required_source_tasks()
    items = await task_repo.list_all()
    canonical_items = [task for task in items if task.name == canonical["name"]]

    assert len(items) == len(NEW_DRUG_SOURCE_TEMPLATES)
    assert len(canonical_items) == 1
    assert canonical_items[0].cron_expr == canonical["cron_expr"]
    assert canonical_items[0].status == int(TaskStatus.ENABLED)
    assert all(task.start_url not in DEMO_TASK_START_URLS for task in items)
    notice_task_id = await async_session.scalar(
        select(CollectedData.task_id).where(CollectedData.content_hash == "duplicate-task-history")
    )
    log_task_id = await async_session.scalar(
        select(LogEntry.task_id).where(LogEntry.message == "duplicate task history")
    )
    assert notice_task_id == canonical_items[0].id == retained_task.id
    assert log_task_id == retained_task.id
