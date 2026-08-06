from datetime import datetime, timezone
import json

import pytest
from sqlalchemy import select

from app.models.data import CollectedData
from app.models.task import Task
from app.repositories.data_repo import DataRepository
from app.schemas.task import TaskStatus


@pytest.mark.asyncio
async def test_create_persists_source_published_at(async_session) -> None:
    async_session.add(
        Task(
            name="Published source",
            start_url="https://gov.example",
            cron_expr="* * * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.flush()
    task_id = (await async_session.execute(select(Task.id))).scalar_one()
    published_at = datetime(2026, 7, 24, 2, 50, 34, tzinfo=timezone.utc)

    row = await DataRepository(async_session).create(
        task_id=task_id,
        title="项目申报通知",
        content_html="<p>正文</p>",
        content_text="正文",
        source_url="https://gov.example/notice/1",
        snapshot_path=None,
        quality_score=80,
        content_hash="published-row",
        published_at=published_at,
    )

    stored_published_at = row.published_at
    if stored_published_at is not None and stored_published_at.tzinfo is None:
        stored_published_at = stored_published_at.replace(tzinfo=timezone.utc)
    assert stored_published_at == published_at


@pytest.mark.asyncio
async def test_list_recent_for_export_all_tasks(async_session) -> None:
    async_session.add(
        Task(
            name="T1",
            start_url="https://a.example",
            cron_expr="* * * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.flush()
    tid = (await async_session.execute(select(Task.id))).scalar_one()
    async_session.add_all(
        [
            CollectedData(
                task_id=tid,
                title="Old",
                content_html=None,
                content_text="a",
                source_url="https://a.example/1",
                snapshot_path=None,
                quality_score=0,
                content_hash=None,
            ),
            CollectedData(
                task_id=tid,
                title="New",
                content_html=None,
                content_text="b",
                source_url="https://a.example/2",
                snapshot_path=None,
                quality_score=0,
                content_hash=None,
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    rows = await repo.list_recent_for_export(task_id=None, limit=10)
    assert len(rows) == 2
    assert rows[0].title == "New"
    assert rows[1].title == "Old"


@pytest.mark.asyncio
async def test_list_recent_for_export_filters_task_id(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="A",
                start_url="https://a.example",
                cron_expr="* * * * *",
                status=1,
            ),
            Task(
                name="B",
                start_url="https://b.example",
                cron_expr="* * * * *",
                status=1,
            ),
        ]
    )
    await async_session.flush()
    ids = (await async_session.execute(select(Task.id).order_by(Task.id))).scalars().all()
    id_a, id_b = ids[0], ids[1]
    async_session.add_all(
        [
            CollectedData(
                task_id=id_a,
                title=None,
                content_html=None,
                content_text="x",
                source_url="https://x/1",
                snapshot_path=None,
                quality_score=0,
                content_hash=None,
            ),
            CollectedData(
                task_id=id_b,
                title=None,
                content_html=None,
                content_text="y",
                source_url="https://y/1",
                snapshot_path=None,
                quality_score=0,
                content_hash=None,
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    rows = await repo.list_recent_for_export(task_id=id_a, limit=10)
    assert len(rows) == 1
    assert rows[0].task_id == id_a


@pytest.mark.asyncio
async def test_list_recent_for_export_omits_irrelevant_project_rows(
    async_session,
) -> None:
    task = Task(
        name="Project source",
        start_url="https://gov.example",
        cron_expr="* * * * *",
        status=1,
    )
    async_session.add(task)
    await async_session.flush()
    async_session.add_all(
        [
            CollectedData(
                task_id=task.id,
                title="公办中小学拟录取名单公示",
                content_text="招生录取安排",
                source_url="https://gov.example/admission",
                quality_score=70,
                content_hash="export-admission-noise",
                category="项目申报",
            ),
            CollectedData(
                task_id=task.id,
                title="重点研发计划项目申报通知",
                content_text="项目申报要求",
                source_url="https://gov.example/project",
                quality_score=70,
                content_hash="export-project-notice",
                category="项目申报",
            ),
        ]
    )
    await async_session.commit()

    rows = await DataRepository(async_session).list_recent_for_export(
        task_id=None,
        limit=10,
    )

    assert [row.title for row in rows] == ["重点研发计划项目申报通知"]


@pytest.mark.asyncio
async def test_list_paginated_no_filters(async_session) -> None:
    async_session.add(
        Task(
            name="T",
            start_url="https://t.example",
            cron_expr="* * * * *",
            status=1,
        )
    )
    await async_session.flush()
    tid = (await async_session.execute(select(Task.id))).scalar_one()
    async_session.add(
        CollectedData(
            task_id=tid,
            title="Row",
            content_html=None,
            content_text="body",
            source_url="https://t.example/p",
            snapshot_path=None,
            quality_score=1,
            content_hash="h1",
        )
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    items, total = await repo.list_paginated(page=1, page_size=20)
    assert total == 1
    assert len(items) == 1
    assert items[0].source_url == "https://t.example/p"


@pytest.mark.asyncio
async def test_list_paginated_keyword_hits_first(async_session) -> None:
    async_session.add(
        Task(
            name="T",
            start_url="https://t.example",
            cron_expr="* * * * *",
            status=1,
        )
    )
    await async_session.flush()
    tid = (await async_session.execute(select(Task.id))).scalar_one()
    async_session.add_all(
        [
            CollectedData(
                task_id=tid,
                title="No hit newer",
                content_html=None,
                content_text="plain body",
                source_url="https://t.example/newer",
                snapshot_path=None,
                quality_score=1,
                content_hash="h-newer",
            ),
            CollectedData(
                task_id=tid,
                title="Older 招标公告",
                content_html=None,
                content_text="older",
                source_url="https://t.example/older",
                snapshot_path=None,
                quality_score=1,
                content_hash="h-older",
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    items, total = await repo.list_paginated(
        page=1,
        page_size=10,
        enabled_only=True,
        active_keywords_for_sort=["招标"],
    )
    assert total == 2
    assert [row.title for row in items] == ["Older 招标公告", "No hit newer"]


@pytest.mark.asyncio
async def test_list_paginated_enabled_only_hides_task_entry_pages(async_session) -> None:
    async_session.add(
        Task(
            name="T",
            start_url="https://service.example/xmtj/",
            cron_expr="* * * * *",
            status=1,
        )
    )
    await async_session.flush()
    tid = (await async_session.execute(select(Task.id))).scalar_one()
    async_session.add_all(
        [
            CollectedData(
                task_id=tid,
                title="入口页",
                content_html=None,
                content_text="portal",
                source_url="https://service.example/xmtj/",
                snapshot_path=None,
                quality_score=1,
                content_hash="entry",
            ),
            CollectedData(
                task_id=tid,
                title="通知详情",
                content_html=None,
                content_text="detail",
                source_url="https://service.example/kjjh_tztg_all/1.html",
                snapshot_path=None,
                quality_score=80,
                content_hash="detail",
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    items, total = await repo.list_paginated(page=1, page_size=10, enabled_only=True)

    assert total == 1
    assert len(items) == 1
    assert items[0].title == "通知详情"


@pytest.mark.asyncio
async def test_list_paginated_includes_manual_source_items_from_disabled_task(async_session) -> None:
    async_session.add(
        Task(
            name="公众号人工链接",
            start_url="https://mp.weixin.qq.com/",
            parser_rules='{"collection_mode": "manual"}',
            cron_expr="0 9 * * *",
            status=int(TaskStatus.DISABLED),
        )
    )
    await async_session.flush()
    task_id = (await async_session.execute(select(Task.id))).scalar_one()
    async_session.add(
        CollectedData(
            task_id=task_id,
            title="公众号项目申报通知",
            content_html="<p>正文</p>",
            content_text="正文",
            source_url="https://mp.weixin.qq.com/s/example",
            snapshot_path=None,
            quality_score=80,
            content_hash="manual-wechat",
        )
    )
    await async_session.commit()

    items, total = await DataRepository(async_session).list_paginated(
        page=1,
        page_size=10,
        enabled_only=True,
    )

    assert total == 1
    assert [item.title for item in items] == ["公众号项目申报通知"]


@pytest.mark.asyncio
async def test_list_paginated_filters_information_pool_metadata(async_session) -> None:
    async_session.add(
        Task(
            name="T",
            start_url="https://t.example",
            cron_expr="* * * * *",
            status=1,
        )
    )
    await async_session.flush()
    tid = (await async_session.execute(select(Task.id))).scalar_one()
    async_session.add_all(
        [
            CollectedData(
                task_id=tid,
                title="项目申报通知",
                content_html=None,
                content_text="申报方向：生物医药",
                source_url="https://gov.example/notice",
                snapshot_path=None,
                quality_score=80,
                content_hash="pool-1",
                category="项目申报",
                review_status="待关注",
                is_archived=False,
            ),
            CollectedData(
                task_id=tid,
                title="行业会议",
                content_html=None,
                content_text="会议报名",
                source_url="https://meet.example/a",
                snapshot_path=None,
                quality_score=60,
                content_hash="pool-2",
                category="行业会议",
                review_status="有效",
                is_archived=True,
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    items, total = await repo.list_paginated(
        page=1,
        page_size=10,
        category="项目申报",
        review_status="待关注",
        archived=False,
    )

    assert total == 1
    assert items[0].title == "项目申报通知"


@pytest.mark.asyncio
async def test_project_signal_counts_match_filtered_lists_and_exclude_non_project_noise(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="科技厅项目申报采集",
                start_url="https://project.example/root",
                cron_expr="* * * * *",
                status=1,
            ),
            Task(
                name="中国药学会会议信息采集",
                start_url="https://meeting.example/root",
                parser_rules=json.dumps({"category": "行业会议"}, ensure_ascii=False),
                cron_expr="* * * * *",
                status=1,
            ),
            Task(
                name="竞品情报采集",
                start_url="https://competitor.example/root",
                parser_rules=json.dumps({"category": "竞品信息"}, ensure_ascii=False),
                cron_expr="* * * * *",
                status=1,
            ),
        ]
    )
    await async_session.flush()
    task_ids = (await async_session.execute(select(Task.id).order_by(Task.id))).scalars().all()
    project_task_id, meeting_task_id, competitor_task_id = task_ids[-3:]
    now = datetime.now(timezone.utc)

    async_session.add_all(
        [
            CollectedData(
                task_id=project_task_id,
                title="关于组织申报创新药项目的通知",
                content_html=None,
                content_text="请于截止时间前完成申报",
                source_url="https://project.example/declaration",
                snapshot_path=None,
                quality_score=90,
                content_hash="repo-project-declaration",
                category="项目申报",
                fetch_time=now,
            ),
            CollectedData(
                task_id=project_task_id,
                title="科技计划项目拟立项结果公示",
                content_html=None,
                content_text="现将拟立项结果予以公示",
                source_url="https://project.example/result",
                snapshot_path=None,
                quality_score=70,
                content_hash="repo-project-result",
                category="未分类",
                fetch_time=now,
            ),
            CollectedData(
                task_id=project_task_id,
                title="项目储备需求摸排",
                content_html=None,
                content_text="欢迎提交创新项目方向建议",
                source_url="https://project.example/lead",
                snapshot_path=None,
                quality_score=60,
                content_hash="repo-project-other",
                category="未分类",
                fetch_time=now,
            ),
            CollectedData(
                task_id=meeting_task_id,
                title="学术会议报名通知",
                content_html=None,
                content_text="会议报名已开放，项目申报截止时间见下文",
                source_url="https://meeting.example/notice",
                snapshot_path=None,
                quality_score=50,
                content_hash="repo-meeting-noise",
                category="行业会议",
                metadata_json=json.dumps({"kind": "industry_meeting"}, ensure_ascii=False),
                fetch_time=now,
            ),
            CollectedData(
                task_id=competitor_task_id,
                title="某药物申报结果公示",
                content_html=None,
                content_text="竞品研发进展更新",
                source_url="https://competitor.example/notice",
                snapshot_path=None,
                quality_score=50,
                content_hash="repo-competitor-noise",
                category="竞品信息",
                metadata_json=json.dumps({"kind": "competitor_intelligence"}, ensure_ascii=False),
                fetch_time=now,
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    declarations, declaration_total = await repo.list_paginated(
        page=1,
        page_size=20,
        project_signal="申报通知",
    )
    results, result_total = await repo.list_paginated(
        page=1,
        page_size=20,
        project_signal="结果公示",
    )
    project_other, project_other_total = await repo.list_paginated(
        page=1,
        page_size=20,
        project_signal="其他项目线索",
    )
    counts = dict(await repo.aggregate_project_signals())

    assert declaration_total == 1
    assert [item.title for item in declarations] == ["关于组织申报创新药项目的通知"]
    assert result_total == 1
    assert [item.title for item in results] == ["科技计划项目拟立项结果公示"]
    assert project_other_total == 1
    assert [item.title for item in project_other] == ["项目储备需求摸排"]
    assert counts["申报通知"] == declaration_total
    assert counts["结果公示"] == result_total
    assert counts["其他项目线索"] == project_other_total


@pytest.mark.asyncio
async def test_project_signal_counts_stay_correct_beyond_500_rows(async_session) -> None:
    async_session.add_all(
        [
            Task(
                name="科技厅项目申报采集",
                start_url="https://project.example/root",
                cron_expr="* * * * *",
                status=1,
            ),
            Task(
                name="中国药学会会议信息采集",
                start_url="https://meeting.example/root",
                parser_rules=json.dumps({"category": "行业会议"}, ensure_ascii=False),
                cron_expr="* * * * *",
                status=1,
            ),
        ]
    )
    await async_session.flush()
    task_ids = (await async_session.execute(select(Task.id).order_by(Task.id))).scalars().all()
    project_task_id, meeting_task_id = task_ids[-2:]
    now = datetime.now(timezone.utc)

    async_session.add_all(
        [
            CollectedData(
                task_id=project_task_id,
                title="重点项目申报通知",
                content_html=None,
                content_text="请于截止时间前完成申报",
                source_url="https://project.example/declaration",
                snapshot_path=None,
                quality_score=90,
                content_hash="repo-bulk-project-declaration",
                category="项目申报",
                fetch_time=now,
            ),
            CollectedData(
                task_id=project_task_id,
                title="重点项目结果公示",
                content_html=None,
                content_text="现将拟立项结果予以公示",
                source_url="https://project.example/result",
                snapshot_path=None,
                quality_score=80,
                content_hash="repo-bulk-project-result",
                category="项目申报",
                fetch_time=now,
            ),
            *[
                CollectedData(
                    task_id=meeting_task_id,
                    title=f"会议报名通知 {index}",
                    content_html=None,
                    content_text="会议报名已开放，项目申报截止时间见下文",
                    source_url=f"https://meeting.example/noise/{index}",
                    snapshot_path=None,
                    quality_score=40,
                    content_hash=f"repo-bulk-noise-{index}",
                    category="行业会议",
                    metadata_json=json.dumps({"kind": "industry_meeting"}, ensure_ascii=False),
                    fetch_time=now,
                )
                for index in range(501)
            ],
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    declaration_total = (
        await repo.list_paginated(page=1, page_size=1, project_signal="申报通知")
    )[1]
    result_total = (
        await repo.list_paginated(page=1, page_size=1, project_signal="结果公示")
    )[1]
    counts = dict(await repo.aggregate_project_signals())

    assert declaration_total == 1
    assert result_total == 1
    assert counts["申报通知"] == declaration_total
    assert counts["结果公示"] == result_total
