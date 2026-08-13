from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.models.data import CollectedData
from app.models.keyword_rule import KeywordRule
from app.repositories.data_repo import DataRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskCreate, TaskStatus
from app.services.dashboard_service import DashboardService, _collection_issue_reason
from app.services.keyword_rule_service import KeywordService


def test_collection_issue_reason_explains_network_route_failures() -> None:
    assert _collection_issue_reason(
        status="failed",
        raw_error="Page.goto: net::ERR_CONNECTION_CLOSED at https://service.most.gov.cn/",
        is_stale=True,
    ) == (
        "目标网站连接被中断（ERR_CONNECTION_CLOSED）；"
        "请检查本机代理、TUN 分流或公司网络出口。"
    )
    assert _collection_issue_reason(
        status="failed",
        raw_error="Page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE at http://kjt.hunan.gov.cn/",
        is_stale=True,
    ) == "目标网站返回异常 HTTP 响应；请检查网络分流或网站是否暂时不可用。"


@pytest.mark.asyncio
async def test_dashboard_uses_a_bounded_number_of_database_queries(async_session) -> None:
    engine = async_session.bind.sync_engine
    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        await DashboardService(
            DataRepository(async_session),
            TaskRepository(async_session),
            KeywordRepository(async_session),
        ).get_overview()
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    select_count = sum(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    assert select_count <= 10, statements


@pytest.mark.asyncio
async def test_dashboard_reports_failed_and_stale_collection_tasks(async_session) -> None:
    task_repo = TaskRepository(async_session)
    data_repo = DataRepository(async_session)
    keyword_repo = KeywordRepository(async_session)
    now = datetime.now(timezone.utc)

    task = await task_repo.create(
        TaskCreate(
            name="科技部项目申报采集",
            start_url="https://service.most.gov.cn/kjjh_tztg/",
            parser_rules=None,
            cron_expr="0 8,14 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    task.last_run_status = "failed"
    task.last_run_at = now - timedelta(hours=2)
    task.last_success_at = now - timedelta(days=2)
    task.last_error_message = "network_unreachable"
    healthy_task = await task_repo.create(
        TaskCreate(
            name="行业会议采集",
            start_url="https://conference.example/notices",
            parser_rules=None,
            cron_expr="0 9 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    healthy_task.last_run_status = "success"
    healthy_task.last_run_at = now
    healthy_task.last_success_at = now
    partial_task = await task_repo.create(
        TaskCreate(
            name="广东省科技厅项目申报采集",
            start_url="https://gdstc.gd.gov.cn/notices",
            parser_rules=None,
            cron_expr="5 8,14 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    partial_task.last_run_status = "partial"
    partial_task.last_run_at = now
    partial_task.last_success_at = now
    partial_task.last_error_message = "列表跟进本次有 2 条详情处理失败；最近原因：目标网站请求超时。"
    await async_session.commit()

    overview = await DashboardService(data_repo, task_repo, keyword_repo).get_overview()

    assert overview.collection_health.status == "warning"
    assert overview.collection_health.monitored_task_count == 3
    assert overview.collection_health.failed_task_count == 1
    assert overview.collection_health.partial_task_count == 1
    assert overview.collection_health.stale_task_count == 1
    assert overview.collection_health.last_success_at is not None
    assert overview.collection_health.last_success_at.replace(tzinfo=timezone.utc) == task.last_success_at
    assert overview.collection_health.failed_sources == ["科技部项目申报采集"]
    assert overview.collection_health.partial_sources == ["广东省科技厅项目申报采集"]
    assert [issue.task_id for issue in overview.collection_health.issues] == [task.id, partial_task.id]
    failed_issue, partial_issue = overview.collection_health.issues
    assert failed_issue.status == "failed"
    assert failed_issue.is_stale is True
    assert failed_issue.reason == "网络无法连接（network_unreachable）"
    assert partial_issue.status == "partial"
    assert partial_issue.is_stale is False
    assert partial_issue.reason == "列表跟进本次有 2 条详情处理失败；最近原因：目标网站请求超时。"


@pytest.mark.asyncio
async def test_dashboard_visualizes_project_declarations_and_results(async_session) -> None:
    task_repo = TaskRepository(async_session)
    data_repo = DataRepository(async_session)
    keyword_repo = KeywordRepository(async_session)
    await KeywordService(keyword_repo).ensure_seed_data()

    task = await task_repo.create(
        TaskCreate(
            name="科技厅项目申报采集",
            start_url="https://gov.example/notices",
            parser_rules=None,
            cron_expr="0 8 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    await data_repo.create(
        task_id=task.id,
        title="关于组织申报生物医药项目的通知",
        content_html="<p>项目申报 截止时间</p>",
        content_text="项目申报 截止时间",
        source_url="https://gov.example/a",
        snapshot_path=None,
        quality_score=70,
        content_hash="decl",
        category="项目申报",
        ai_summary="申报通知摘要",
    )
    await data_repo.create(
        task_id=task.id,
        title="科技计划项目拟立项结果公示",
        content_html="<p>结果公示</p>",
        content_text="项目拟立项结果公示",
        source_url="https://gov.example/b",
        snapshot_path=None,
        quality_score=65,
        content_hash="result",
        category="项目申报",
        ai_summary="结果公示摘要",
    )

    overview = await DashboardService(data_repo, task_repo, keyword_repo).get_overview()

    assert overview.metrics.project_declaration_notices == 1
    assert overview.metrics.result_publication_notices == 1
    assert [item.title for item in overview.high_value_notices] == ["关于组织申报生物医药项目的通知"]
    assert [item.label for item in overview.project_signal_distribution[:2]] == ["申报通知", "结果公示"]
    assert overview.project_signal_distribution[0].notice_count == 1


@pytest.mark.asyncio
async def test_dashboard_keeps_disabled_task_history_in_metrics_and_sources(
    async_session,
) -> None:
    task_repo = TaskRepository(async_session)
    data_repo = DataRepository(async_session)
    keyword_repo = KeywordRepository(async_session)
    service = DashboardService(data_repo, task_repo, keyword_repo)

    task = await task_repo.create(
        TaskCreate(
            name="已停用历史来源",
            start_url="https://history.example/root",
            parser_rules=None,
            cron_expr="0 8 * * *",
            status=TaskStatus.DISABLED,
        )
    )
    await data_repo.create(
        task_id=task.id,
        title="历史项目申报通知",
        content_html="<p>项目申报</p>",
        content_text="项目申报",
        source_url="https://history.example/declaration",
        snapshot_path=None,
        quality_score=70,
        content_hash="dashboard-disabled-history",
        category="项目申报",
        ai_summary="历史申报摘要",
    )

    overview = await service.get_overview()
    notices = await service.notice_service.list_notices(
        page=1,
        page_size=1,
        source_site="history.example",
    )

    assert overview.metrics.project_declaration_notices == notices.total == 1
    assert overview.metrics.monitoring_site_count == 0
    assert (
        next(item.notice_count for item in overview.source_distribution if item.source_site == "history.example") == 1
    )
    assert (
        next(item.display_name for item in overview.source_distribution if item.source_site == "history.example")
        == "已停用历史来源"
    )


@pytest.mark.asyncio
async def test_dashboard_recent_notices_ignore_keyword_relevance_sort(async_session) -> None:
    task_repo = TaskRepository(async_session)
    data_repo = DataRepository(async_session)
    keyword_repo = KeywordRepository(async_session)
    now = datetime.now(timezone.utc)

    task = await task_repo.create(
        TaskCreate(
            name="最近公告排序测试",
            start_url="https://recent.example/root",
            parser_rules=None,
            cron_expr="0 8 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    async_session.add_all(
        [
            KeywordRule(word="项目申报", is_active=True),
            CollectedData(
                task_id=task.id,
                title="较早的项目申报通知",
                content_text="项目申报 截止时间",
                source_url="https://recent.example/older",
                quality_score=90,
                content_hash="dashboard-recent-older-hit",
                category="项目申报",
                fetch_time=now - timedelta(days=1),
            ),
            CollectedData(
                task_id=task.id,
                title="刚刚发布的普通公告",
                content_text="一般信息",
                source_url="https://recent.example/newest",
                quality_score=20,
                content_hash="dashboard-recent-newest-no-hit",
                category="未分类",
                fetch_time=now,
            ),
        ]
    )
    await async_session.commit()

    overview = await DashboardService(data_repo, task_repo, keyword_repo).get_overview()

    assert overview.recent_notices[0].title == "刚刚发布的普通公告"
    assert overview.last_updated_at is not None
    assert overview.last_updated_at.replace(tzinfo=timezone.utc) == now


@pytest.mark.asyncio
async def test_dashboard_high_value_notices_keep_quality_first_order(async_session) -> None:
    task_repo = TaskRepository(async_session)
    data_repo = DataRepository(async_session)
    keyword_repo = KeywordRepository(async_session)
    await KeywordService(keyword_repo).ensure_seed_data()
    now = datetime.now(timezone.utc)

    task = await task_repo.create(
        TaskCreate(
            name="业务优先排序测试",
            start_url="https://priority.example/root",
            parser_rules=None,
            cron_expr="0 8 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    async_session.add_all(
        [
            CollectedData(
                task_id=task.id,
                title="较早但完整的项目申报通知",
                content_text="项目申报 截止时间",
                source_url="https://priority.example/complete",
                quality_score=95,
                content_hash="dashboard-priority-high-quality",
                category="项目申报",
                fetch_time=now - timedelta(days=1),
            ),
            CollectedData(
                task_id=task.id,
                title="刚刚发布的项目申报通知",
                content_text="项目申报",
                source_url="https://priority.example/new",
                quality_score=10,
                content_hash="dashboard-priority-low-quality",
                category="项目申报",
                fetch_time=now,
            ),
        ]
    )
    await async_session.commit()

    overview = await DashboardService(data_repo, task_repo, keyword_repo).get_overview()

    assert [item.title for item in overview.high_value_notices[:2]] == [
        "较早但完整的项目申报通知",
        "刚刚发布的项目申报通知",
    ]


@pytest.mark.asyncio
async def test_dashboard_metrics_match_notice_filter_totals_beyond_500_rows(async_session) -> None:
    task_repo = TaskRepository(async_session)
    data_repo = DataRepository(async_session)
    keyword_repo = KeywordRepository(async_session)
    notice_service = DashboardService(data_repo, task_repo, keyword_repo).notice_service
    now = datetime.now(timezone.utc)

    task = await task_repo.create(
        TaskCreate(
            name="大数据量口径测试",
            start_url="https://bulk.example/root",
            parser_rules=None,
            cron_expr="0 8 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    async_session.add_all(
        [
            KeywordRule(word="医药", is_active=True),
            CollectedData(
                task_id=task.id,
                title="重点项目申报通知",
                content_text="申报截止时间",
                source_url="https://signals.example/declaration",
                quality_score=90,
                content_hash="dashboard-declaration",
                category="项目申报",
                fetch_time=now - timedelta(hours=3),
            ),
            CollectedData(
                task_id=task.id,
                title="项目结果公示",
                content_text="拟立项结果公示",
                source_url="https://signals.example/result",
                quality_score=30,
                content_hash="dashboard-result",
                category="项目申报",
                fetch_time=now - timedelta(hours=2),
            ),
            CollectedData(
                task_id=task.id,
                title="最新系统提醒",
                content_text="一般信息",
                source_url="https://alerts.example/latest",
                quality_score=20,
                content_hash="dashboard-latest-non-hit",
                category="未分类",
                fetch_time=now,
            ),
            CollectedData(
                task_id=task.id,
                title="今天补采的历史公告",
                content_text="一般信息",
                source_url="https://alerts.example/historical-backfill",
                quality_score=20,
                content_hash="dashboard-historical-backfill",
                category="未分类",
                published_at=now - timedelta(days=30),
                fetch_time=now - timedelta(minutes=1),
            ),
            *[
                CollectedData(
                    task_id=task.id,
                    title=f"医药普通动态 {index}",
                    content_text="一般信息",
                    source_url=f"https://bulk.example/items/{index}",
                    quality_score=10,
                    content_hash=f"dashboard-filler-{index}",
                    category="未分类",
                    fetch_time=now - timedelta(hours=1),
                )
                for index in range(501)
            ],
        ]
    )
    await async_session.commit()
    await KeywordService(keyword_repo).ensure_seed_data()

    overview = await DashboardService(data_repo, task_repo, keyword_repo).get_overview()
    today = await notice_service.list_notices(page=1, page_size=1, business_today=True)
    captured_today = await notice_service.list_notices(page=1, page_size=1, captured_today=True)
    keyword_hits = await notice_service.list_notices(page=1, page_size=1, keyword_hit=True)
    medical_keyword = await notice_service.list_notices(page=1, page_size=1, keyword="医药")
    bulk_source = await notice_service.list_notices(page=1, page_size=1, source_site="bulk.example")
    high_priority = await notice_service.list_notices(page=1, page_size=1, high_priority=True)
    high_quality = await notice_service.list_notices(page=1, page_size=1, high_quality=True)
    declarations = await notice_service.list_notices(page=1, page_size=1, project_signal="申报通知")
    results = await notice_service.list_notices(page=1, page_size=1, project_signal="结果公示")

    assert overview.metrics.today_new_notices == today.total == 504
    assert captured_today.total == 505
    assert overview.metrics.keyword_hit_notices == keyword_hits.total == 503
    assert overview.metrics.high_priority_notices == high_priority.total == 1
    assert overview.metrics.high_quality_notices == high_quality.total == 1
    assert overview.metrics.project_declaration_notices == declarations.total == 1
    assert overview.metrics.result_publication_notices == results.total == 1
    assert next(item.count for item in overview.keyword_heat if item.keyword == "医药") == medical_keyword.total == 501
    assert (
        next(item.notice_count for item in overview.source_distribution if item.source_site == "bulk.example")
        == bulk_source.total
        == 501
    )
    assert (
        next(item.notice_count for item in overview.project_signal_distribution if item.label == "申报通知")
        == declarations.total
        == 1
    )
    assert (
        next(item.notice_count for item in overview.project_signal_distribution if item.label == "结果公示")
        == results.total
        == 1
    )
    assert overview.recent_notices[0].title == "最新系统提醒"
    assert overview.last_updated_at is not None
    assert overview.last_updated_at.replace(tzinfo=timezone.utc) == now
    assert sum(item.notice_count for item in overview.source_distribution) == 505


@pytest.mark.asyncio
async def test_dashboard_high_value_notices_are_not_limited_by_first_500_rows(async_session) -> None:
    task_repo = TaskRepository(async_session)
    data_repo = DataRepository(async_session)
    keyword_repo = KeywordRepository(async_session)
    await KeywordService(keyword_repo).ensure_seed_data()

    task = await task_repo.create(
        TaskCreate(
            name="国家药监局项目申报通知采集",
            start_url="https://nmpa.example/root",
            parser_rules=None,
            cron_expr="0 8 * * *",
            status=TaskStatus.ENABLED,
        )
    )
    older_priority = CollectedData(
        task_id=task.id,
        title="创新药项目申报通知",
        content_text="项目申报 截止时间",
        source_url="https://nmpa.example/high-value",
        quality_score=95,
        content_hash="dashboard-older-priority",
        category="项目申报",
    )
    async_session.add_all(
        [
            older_priority,
            *[
                CollectedData(
                    task_id=task.id,
                    title=f"普通公告 {index}",
                    content_text="一般信息",
                    source_url=f"https://nmpa.example/items/{index}",
                    quality_score=10,
                    content_hash=f"dashboard-recent-filler-{index}",
                    category="未分类",
                )
                for index in range(501)
            ],
        ]
    )
    await async_session.commit()

    older_priority.fetch_time = older_priority.fetch_time.replace(year=older_priority.fetch_time.year - 1)
    await async_session.commit()

    overview = await DashboardService(data_repo, task_repo, keyword_repo).get_overview()

    assert overview.metrics.high_priority_notices == 1
    assert [item.title for item in overview.high_value_notices] == ["创新药项目申报通知"]
    assert overview.source_distribution[0].display_name == "国家药监局项目申报通知"
