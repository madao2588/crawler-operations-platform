from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

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
async def test_collect_manual_source_accepts_only_fixed_wechat_source_and_host(async_session) -> None:
    class FakeCrawlService:
        def __init__(self) -> None:
            self.calls: list[tuple[int, str]] = []

        async def collect_manual_url(self, task_id: int, url: str):
            self.calls.append((task_id, url))
            return {
                "status": "stored",
                "notice_id": 88,
                "source_url": url,
            }

    task_repo = TaskRepository(async_session)
    log_repo = LogRepository(async_session)
    crawl_service = FakeCrawlService()
    service = TaskService(
        task_repo=task_repo,
        log_repo=log_repo,
        crawl_service=crawl_service,  # type: ignore[arg-type]
    )
    await service.ensure_required_source_tasks()
    article_url = "https://mp.weixin.qq.com/s/example-article"

    result = await service.collect_manual_source("wechat_k_innovation", article_url)

    assert result.status == "stored"
    assert result.notice_id == 88
    assert result.source_url == article_url
    assert len(crawl_service.calls) == 1

    with pytest.raises(ValueError, match="mp.weixin.qq.com"):
        await service.collect_manual_source(
            "wechat_k_innovation",
            "https://example.com/not-wechat",
        )
    with pytest.raises(ValueError, match="manual collection"):
        await service.collect_manual_source(
            "most_project_declaration",
            article_url,
        )


@pytest.mark.asyncio
async def test_collect_manual_source_rejects_allowed_host_that_resolves_private_ip(async_session, monkeypatch) -> None:
    class FakeCrawlService:
        async def collect_manual_url(self, _task_id: int, _url: str):
            raise AssertionError("should not collect unsafe manual URL")

    task_repo = TaskRepository(async_session)
    log_repo = LogRepository(async_session)
    service = TaskService(
        task_repo=task_repo,
        log_repo=log_repo,
        crawl_service=FakeCrawlService(),  # type: ignore[arg-type]
    )
    await service.ensure_required_source_tasks()

    def fake_assert_safe_outbound_url(_url: str) -> str:
        from app.utils.url_security import UnsafeTargetError

        raise UnsafeTargetError("Resolved address 10.0.0.10 for host mp.weixin.qq.com is not public")

    monkeypatch.setattr("app.services.task_service.assert_safe_outbound_url", fake_assert_safe_outbound_url)

    with pytest.raises(ValueError, match="not public"):
        await service.collect_manual_source(
            "wechat_k_innovation",
            "https://mp.weixin.qq.com/s/private-hop",
        )
