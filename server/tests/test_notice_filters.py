from datetime import datetime, timedelta, timezone
import json

import pytest

import app.repositories.data_repo as data_repo_module
from app.api.v1.notice import list_notices as list_notices_endpoint
from app.models.data import CollectedData
from app.models.keyword_rule import KeywordRule
from app.models.task import Task
from app.repositories.data_repo import DataRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.schemas.common import PageData
from app.services.notice_service import NoticeService
from app.services.keyword_rule_service import KeywordService


async def _seed_filter_rows(async_session) -> NoticeService:
    task = Task(
        name="筛选测试任务采集",
        start_url="https://portal.example/root",
        cron_expr="0 8 * * *",
        status=1,
    )
    async_session.add(task)
    await async_session.flush()

    now = datetime.now(timezone.utc)
    async_session.add_all(
        [
            KeywordRule(word="重点研发", is_high_priority=True, is_active=True),
            CollectedData(
                task_id=task.id,
                title="重点研发项目申报通知",
                content_text="请在截止时间前完成申报",
                source_url="https://alpha.example/notices/declaration",
                quality_score=30,
                content_hash="filter-declaration",
                category="项目申报",
                fetch_time=now,
            ),
            CollectedData(
                task_id=task.id,
                title="科技计划项目结果公示",
                content_text="拟立项结果公示",
                source_url="https://beta.example/notices/result",
                quality_score=65,
                content_hash="filter-result",
                category="项目申报",
                fetch_time=now,
            ),
            CollectedData(
                task_id=task.id,
                title="普通工作动态",
                content_text="没有业务标签",
                source_url="https://alpha.example/notices/plain",
                quality_score=10,
                content_hash="filter-plain-today",
                category="未分类",
                fetch_time=now,
            ),
            CollectedData(
                task_id=task.id,
                title="临床研究进展",
                content_text="历史信息",
                source_url="https://gamma.example/notices/old",
                quality_score=20,
                content_hash="filter-keyword-old",
                category="竞品信息",
                fetch_time=now - timedelta(days=1),
            ),
            CollectedData(
                task_id=task.id,
                title="项目工作简报",
                content_text="其他事项",
                source_url="https://alpha.example/notices/project-other",
                quality_score=10,
                content_hash="filter-project-other",
                category="项目申报",
                fetch_time=now,
            ),
        ]
    )
    await async_session.commit()
    keyword_repo = KeywordRepository(async_session)
    await KeywordService(keyword_repo).ensure_seed_data()
    return NoticeService(
        data_repo=DataRepository(async_session),
        keyword_repo=keyword_repo,
    )


@pytest.mark.asyncio
async def test_notice_filters_each_supported_dimension(async_session) -> None:
    service = await _seed_filter_rows(async_session)

    today = await service.list_notices(page=1, page_size=20, captured_today=True)
    not_today = await service.list_notices(page=1, page_size=20, captured_today=False)
    source = await service.list_notices(page=1, page_size=20, source_site="alpha.example")
    keyword_hits = await service.list_notices(page=1, page_size=20, keyword_hit=True)
    no_keyword_hits = await service.list_notices(page=1, page_size=20, keyword_hit=False)
    high_priority = await service.list_notices(page=1, page_size=20, high_priority=True)
    high_quality = await service.list_notices(page=1, page_size=20, high_quality=True)
    declaration = await service.list_notices(page=1, page_size=20, project_signal="申报通知")
    result = await service.list_notices(page=1, page_size=20, project_signal="结果公示")
    project_other = await service.list_notices(page=1, page_size=20, project_signal="其他项目线索")

    assert today.total == 4
    assert not_today.total == 1
    assert source.total == 3
    assert keyword_hits.total == 3
    assert no_keyword_hits.total == 2
    assert high_priority.total == 2
    assert {item.title for item in high_priority.items} == {
        "重点研发项目申报通知",
        "临床研究进展",
    }
    assert high_quality.total == 1
    assert [item.title for item in high_quality.items] == ["科技计划项目结果公示"]
    assert [item.id for item in declaration.items] == [1]
    assert declaration.items[0].project_signal == "申报通知"
    assert [item.id for item in result.items] == [2]
    assert result.items[0].project_signal == "结果公示"
    assert [item.id for item in project_other.items] == [5]
    assert project_other.items[0].project_signal == "其他项目线索"


@pytest.mark.asyncio
async def test_notice_source_site_options_are_unique_and_stably_ranked(async_session) -> None:
    service = await _seed_filter_rows(async_session)

    options = await service.list_source_sites()

    assert [(option.source_site, option.display_name) for option in options] == [
        ("alpha.example", "筛选测试任务"),
        ("beta.example", "筛选测试任务"),
        ("gamma.example", "筛选测试任务"),
    ]


@pytest.mark.asyncio
async def test_notice_results_hide_irrelevant_rows_from_project_sources(
    async_session,
) -> None:
    task = Task(
        name="横琴项目申报采集",
        start_url="https://gov.example/root",
        cron_expr="0 8 * * *",
        status=1,
    )
    async_session.add(task)
    await async_session.flush()
    async_session.add_all(
        [
            CollectedData(
                task_id=task.id,
                title="关于2026年秋季公办中小学拟录取名单的公示",
                content_text="招生录取安排",
                source_url="https://gov.example/notices/admission",
                quality_score=70,
                content_hash="irrelevant-admission",
                category="项目申报",
                metadata_json=json.dumps({"kind": "project_notice"}),
            ),
            CollectedData(
                task_id=task.id,
                title="关于重点研发计划项目拟立项名单的公示",
                content_text="本批项目评审结果如下",
                source_url="https://gov.example/notices/project-result",
                quality_score=70,
                content_hash="relevant-project-result",
                category="项目申报",
                metadata_json=json.dumps({"kind": "project_notice"}),
            ),
            CollectedData(
                task_id=task.id,
                title="澳门青年创业企业办公场地租金和物业管理费补贴拟发放名单公示",
                content_text="现将企业补贴拟发放名单予以公示",
                source_url="https://gov.example/notices/startup-subsidy-result",
                quality_score=70,
                content_hash="relevant-startup-subsidy-result",
                category="项目申报",
                metadata_json=json.dumps({"kind": "project_notice"}),
            ),
            CollectedData(
                task_id=task.id,
                title="竞品企业招聘动态",
                content_text="招聘信息",
                source_url="https://gov.example/notices/competitor",
                quality_score=60,
                content_hash="non-project-recruitment",
                category="竞品信息",
                metadata_json=json.dumps({"kind": "competitor_intelligence"}),
            ),
        ]
    )
    await async_session.commit()
    service = NoticeService(
        data_repo=DataRepository(async_session),
        keyword_repo=KeywordRepository(async_session),
    )

    notices = await service.list_notices(page=1, page_size=20)
    project_signals = await service.data_repo.aggregate_project_signals(
        enabled_only=True,
        include_disabled_history=True,
    )

    assert notices.total == 3
    assert {item.title for item in notices.items} == {
        "关于重点研发计划项目拟立项名单的公示",
        "澳门青年创业企业办公场地租金和物业管理费补贴拟发放名单公示",
        "竞品企业招聘动态",
    }
    assert sum(count for _, count in project_signals) == 2


@pytest.mark.asyncio
async def test_project_signal_filter_uses_title_first_and_covers_official_result_phrases(
    async_session,
) -> None:
    task = Task(
        name="科技厅项目申报采集",
        start_url="https://gov.example/notices",
        cron_expr="0 8 * * *",
        status=1,
        parser_rules=json.dumps({"category": "项目申报"}),
    )
    async_session.add(task)
    await async_session.flush()
    rows = [
        (
            "关于发布重点研发计划项目申报指南的通知",
            "项目申报后将组织评审，评审结果和拟入库情况另行通知。",
            "title-first-declaration",
        ),
        (
            "关于开展2027年度人工智能项目入库储备工作的通知",
            "申报单位请按照申报指南提交材料。",
            "storage-declaration",
        ),
        (
            "关于科技项目审核结果的公示",
            "现将通过审核的项目予以公示。",
            "audit-result",
        ),
        (
            "关于科技项目验收结论的公示",
            "项目验收工作已经完成。",
            "acceptance-result",
        ),
        (
            "2026年科技人才计划支持经费公示",
            "现将支持对象和经费予以公示。",
            "funding-result",
        ),
        (
            "关于公布重点研发计划立项名单的通知",
            "现公布本批立项项目名单。",
            "project-list-result",
        ),
        (
            "关于开展2026年度科技项目验收工作的通知",
            "请项目承担单位提交验收材料。",
            "acceptance-process",
        ),
        (
            "关于发布2027年度揭榜挂帅项目榜单的通知",
            "项目入选后将另行公示拟立项结果。",
            "challenge-list-declaration",
        ),
        (
            "关于生物医药产业临床试验视同立项项目公示",
            "现将视同立项项目予以公示。",
            "deemed-approved-result",
        ),
        (
            "关于科技型企业拟登记名单的公示",
            "申报材料审核完成，现公示拟登记名单。",
            "registration-list-result",
        ),
        (
            "关于开展2026年度专项项目验收工作的通知",
            "验收工作完成后将另行公示验收结果。",
            "acceptance-process-with-result-body",
        ),
        (
            "广东省2026年第五批拟更名高新技术企业名单公示",
            "现将拟更名企业名单予以公示。",
            "renamed-enterprise-list",
        ),
        (
            "广东省异地搬迁高新技术企业名单公示",
            "现将异地搬迁企业名单予以公示。",
            "relocated-enterprise-list",
        ),
        (
            "创新药品医疗器械目录公示",
            "现将目录内容予以公示。",
            "product-directory",
        ),
        (
            "琴澳健康小妙想作品征集活动获奖名单公示",
            "现将活动获奖名单予以公示。",
            "creative-works-award",
        ),
    ]
    async_session.add_all(
        [
            CollectedData(
                task_id=task.id,
                title=title,
                content_text=content,
                source_url=f"https://gov.example/notices/{content_hash}",
                quality_score=80,
                content_hash=content_hash,
                category="项目申报",
                metadata_json=json.dumps({"kind": "project_notice"}),
            )
            for title, content, content_hash in rows
        ]
    )
    await async_session.commit()
    service = NoticeService(
        data_repo=DataRepository(async_session),
        keyword_repo=KeywordRepository(async_session),
    )

    declarations = await service.list_notices(
        page=1,
        page_size=20,
        project_signal="申报通知",
    )
    results = await service.list_notices(
        page=1,
        page_size=20,
        project_signal="结果公示",
    )
    other = await service.list_notices(
        page=1,
        page_size=20,
        project_signal="其他项目线索",
    )

    assert {item.title for item in declarations.items} == {
        "关于发布重点研发计划项目申报指南的通知",
        "关于开展2027年度人工智能项目入库储备工作的通知",
        "关于发布2027年度揭榜挂帅项目榜单的通知",
    }
    assert {item.title for item in results.items} == {
        "关于科技项目审核结果的公示",
        "关于科技项目验收结论的公示",
        "2026年科技人才计划支持经费公示",
        "关于公布重点研发计划立项名单的通知",
        "关于生物医药产业临床试验视同立项项目公示",
        "关于科技型企业拟登记名单的公示",
    }
    assert {item.title for item in other.items} == {
        "关于开展2026年度科技项目验收工作的通知",
        "关于开展2026年度专项项目验收工作的通知",
        "广东省2026年第五批拟更名高新技术企业名单公示",
        "广东省异地搬迁高新技术企业名单公示",
        "创新药品医疗器械目录公示",
        "琴澳健康小妙想作品征集活动获奖名单公示",
    }
    assert {item.project_signal for item in declarations.items} == {"申报通知"}
    assert {item.project_signal for item in results.items} == {"结果公示"}
    assert {item.project_signal for item in other.items} == {"其他项目线索"}


@pytest.mark.asyncio
async def test_disabled_task_history_stays_visible_in_notices_and_source_options(
    async_session,
) -> None:
    task = Task(
        name="历史来源采集",
        start_url="https://history.example/root",
        cron_expr="0 8 * * *",
        status=0,
    )
    async_session.add(task)
    await async_session.flush()
    async_session.add(
        CollectedData(
            task_id=task.id,
            title="历史项目申报通知",
            content_text="已经采集的数据不应因任务停用而消失",
            source_url="https://history.example/notices/1",
            quality_score=80,
            content_hash="disabled-task-history",
            category="项目申报",
        )
    )
    await async_session.commit()
    service = NoticeService(
        data_repo=DataRepository(async_session),
        keyword_repo=KeywordRepository(async_session),
    )

    notices = await service.list_notices(
        page=1,
        page_size=20,
        source_site="history.example",
    )
    options = await service.list_source_sites()

    assert notices.total == 1
    assert notices.items[0].title == "历史项目申报通知"
    assert any(option.source_site == "history.example" and option.display_name == "历史来源" for option in options)


def test_notice_source_site_options_endpoint(
    asgi_test_client,
    auth_headers: dict[str, str],
) -> None:
    response = asgi_test_client.get(
        "/v1/notices/source-sites",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert all(set(option) == {"source_site", "display_name"} for option in data)


@pytest.mark.asyncio
async def test_notice_filters_can_be_combined_without_changing_pagination_total(async_session) -> None:
    service = await _seed_filter_rows(async_session)

    combined = await service.list_notices(
        page=1,
        page_size=1,
        captured_today=True,
        source_site="alpha.example",
        keyword_hit=True,
        high_priority=True,
        high_quality=False,
        project_signal="申报通知",
    )

    assert combined.total == 1
    assert len(combined.items) == 1
    assert combined.items[0].title == "重点研发项目申报通知"


@pytest.mark.asyncio
async def test_project_signal_filters_only_count_project_context_not_meetings_or_competitors(async_session) -> None:
    project_task = Task(
        name="科技厅项目申报采集",
        start_url="https://project.example/root",
        cron_expr="0 8 * * *",
        status=1,
    )
    meeting_task = Task(
        name="中国药学会会议信息采集",
        start_url="https://meeting.example/root",
        parser_rules=json.dumps({"category": "行业会议"}, ensure_ascii=False),
        cron_expr="0 8 * * *",
        status=1,
    )
    competitor_task = Task(
        name="竞品情报采集",
        start_url="https://competitor.example/root",
        parser_rules=json.dumps({"category": "竞品信息"}, ensure_ascii=False),
        cron_expr="0 8 * * *",
        status=1,
    )
    async_session.add_all([project_task, meeting_task, competitor_task])
    await async_session.flush()

    now = datetime.now(timezone.utc)
    async_session.add_all(
        [
            CollectedData(
                task_id=project_task.id,
                title="关于组织申报创新药项目的通知",
                content_text="请于截止时间前提交材料",
                source_url="https://project.example/declaration",
                quality_score=80,
                content_hash="project-signal-declaration",
                category="项目申报",
                fetch_time=now,
            ),
            CollectedData(
                task_id=project_task.id,
                title="科技计划项目拟立项结果公示",
                content_text="现将拟立项结果予以公示",
                source_url="https://project.example/result",
                quality_score=80,
                content_hash="project-signal-result",
                category="未分类",
                fetch_time=now,
            ),
            CollectedData(
                task_id=meeting_task.id,
                title="学术会议报名通知",
                content_text="会议报名已开放，项目申报截止时间见下文",
                source_url="https://meeting.example/notice",
                quality_score=50,
                content_hash="project-signal-meeting-noise",
                category="行业会议",
                metadata_json=json.dumps({"kind": "industry_meeting"}, ensure_ascii=False),
                fetch_time=now,
            ),
            CollectedData(
                task_id=competitor_task.id,
                title="某药物申报结果公示",
                content_text="竞品研发进展更新",
                source_url="https://competitor.example/notice",
                quality_score=50,
                content_hash="project-signal-competitor-noise",
                category="竞品信息",
                metadata_json=json.dumps({"kind": "competitor_intelligence"}, ensure_ascii=False),
                fetch_time=now,
            ),
        ]
    )
    await async_session.commit()

    service = NoticeService(
        data_repo=DataRepository(async_session),
        keyword_repo=KeywordRepository(async_session),
    )

    declarations = await service.list_notices(page=1, page_size=20, project_signal="申报通知")
    results = await service.list_notices(page=1, page_size=20, project_signal="结果公示")

    assert declarations.total == 1
    assert [item.title for item in declarations.items] == ["关于组织申报创新药项目的通知"]
    assert results.total == 1
    assert [item.title for item in results.items] == ["科技计划项目拟立项结果公示"]


@pytest.mark.asyncio
async def test_captured_today_uses_shanghai_midnight_as_utc_half_open_range(
    async_session,
    monkeypatch,
) -> None:
    task = Task(
        name="上海业务日边界",
        start_url="https://boundary.example/root",
        cron_expr="0 8 * * *",
        status=1,
    )
    async_session.add(task)
    await async_session.flush()

    start = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
    end = datetime(2026, 7, 29, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        data_repo_module,
        "_shanghai_business_day_utc_bounds",
        lambda: (start, end),
        raising=False,
    )
    async_session.add_all(
        [
            CollectedData(
                task_id=task.id,
                title="开始前",
                content_text="boundary",
                source_url="https://boundary.example/before",
                quality_score=10,
                content_hash="boundary-before",
                fetch_time=start - timedelta(microseconds=1),
            ),
            CollectedData(
                task_id=task.id,
                title="恰好开始",
                content_text="boundary",
                source_url="https://boundary.example/start",
                quality_score=10,
                content_hash="boundary-start",
                fetch_time=start,
            ),
            CollectedData(
                task_id=task.id,
                title="结束前",
                content_text="boundary",
                source_url="https://boundary.example/end-before",
                quality_score=10,
                content_hash="boundary-end-before",
                fetch_time=end - timedelta(microseconds=1),
            ),
            CollectedData(
                task_id=task.id,
                title="恰好结束",
                content_text="boundary",
                source_url="https://boundary.example/end",
                quality_score=10,
                content_hash="boundary-end",
                fetch_time=end,
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    today, today_total = await repo.list_paginated(
        page=1,
        page_size=20,
        enabled_only=True,
        captured_today=True,
    )
    outside, outside_total = await repo.list_paginated(
        page=1,
        page_size=20,
        enabled_only=True,
        captured_today=False,
    )

    assert today_total == 2
    assert {item.title for item in today} == {"恰好开始", "结束前"}
    assert outside_total == 2
    assert {item.title for item in outside} == {"开始前", "恰好结束"}


@pytest.mark.asyncio
async def test_business_today_prefers_published_date_and_falls_back_to_capture_date(
    async_session,
    monkeypatch,
) -> None:
    task = Task(
        name="项目申报业务日期筛选",
        start_url="https://business-date.example/root",
        cron_expr="0 8 * * *",
        status=1,
    )
    async_session.add(task)
    await async_session.flush()

    start = datetime(2026, 7, 28, 16, 0, tzinfo=timezone.utc)
    end = datetime(2026, 7, 29, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        data_repo_module,
        "_shanghai_business_day_utc_bounds",
        lambda: (start, end),
        raising=False,
    )
    async_session.add_all(
        [
            CollectedData(
                task_id=task.id,
                title="今日发布但早先采集",
                content_text="项目申报",
                source_url="https://business-date.example/published-today",
                quality_score=10,
                content_hash="business-published-today",
                category="项目申报",
                published_at=start,
                fetch_time=start - timedelta(days=3),
            ),
            CollectedData(
                task_id=task.id,
                title="历史发布但今日补采",
                content_text="项目申报",
                source_url="https://business-date.example/captured-today",
                quality_score=10,
                content_hash="business-captured-today",
                category="项目申报",
                published_at=start - timedelta(days=3),
                fetch_time=start,
            ),
            CollectedData(
                task_id=task.id,
                title="缺少发布日期且今日采集",
                content_text="项目申报",
                source_url="https://business-date.example/fallback-today",
                quality_score=10,
                content_hash="business-fallback-today",
                category="项目申报",
                published_at=None,
                fetch_time=end - timedelta(microseconds=1),
            ),
            CollectedData(
                task_id=task.id,
                title="缺少发布日期且历史采集",
                content_text="项目申报",
                source_url="https://business-date.example/fallback-old",
                quality_score=10,
                content_hash="business-fallback-old",
                category="项目申报",
                published_at=None,
                fetch_time=start - timedelta(microseconds=1),
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    today, today_total = await repo.list_paginated(
        page=1,
        page_size=20,
        enabled_only=True,
        business_today=True,
    )
    outside, outside_total = await repo.list_paginated(
        page=1,
        page_size=20,
        enabled_only=True,
        business_today=False,
    )

    assert today_total == 2
    assert {item.title for item in today} == {
        "今日发布但早先采集",
        "缺少发布日期且今日采集",
    }
    assert outside_total == 2
    assert {item.title for item in outside} == {
        "历史发布但今日补采",
        "缺少发布日期且历史采集",
    }


@pytest.mark.asyncio
async def test_business_week_prefers_published_date_and_falls_back_to_capture_date(
    async_session,
    monkeypatch,
) -> None:
    task = Task(
        name="本周业务日期筛选",
        start_url="https://business-week.example/root",
        cron_expr="0 8 * * *",
        status=1,
    )
    async_session.add(task)
    await async_session.flush()

    start = datetime(2026, 8, 9, 16, 0, tzinfo=timezone.utc)
    end = datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        data_repo_module,
        "_shanghai_business_week_utc_bounds",
        lambda: (start, end),
        raising=False,
    )
    async_session.add_all(
        [
            CollectedData(
                task_id=task.id,
                title="本周发布但早先采集",
                content_text="项目申报",
                source_url="https://business-week.example/published-this-week",
                quality_score=10,
                content_hash="business-published-this-week",
                category="项目申报",
                published_at=start,
                fetch_time=start - timedelta(days=5),
            ),
            CollectedData(
                task_id=task.id,
                title="上周发布但本周补采",
                content_text="项目申报",
                source_url="https://business-week.example/captured-this-week",
                quality_score=10,
                content_hash="business-captured-this-week",
                category="项目申报",
                published_at=start - timedelta(microseconds=1),
                fetch_time=start,
            ),
            CollectedData(
                task_id=task.id,
                title="缺少发布日期且本周采集",
                content_text="项目申报",
                source_url="https://business-week.example/fallback-this-week",
                quality_score=10,
                content_hash="business-fallback-this-week",
                category="项目申报",
                published_at=None,
                fetch_time=end - timedelta(microseconds=1),
            ),
            CollectedData(
                task_id=task.id,
                title="本周范围结束后的公告",
                content_text="项目申报",
                source_url="https://business-week.example/after-this-week",
                quality_score=10,
                content_hash="business-after-this-week",
                category="项目申报",
                published_at=end,
                fetch_time=end,
            ),
        ]
    )
    await async_session.commit()

    repo = DataRepository(async_session)
    this_week, this_week_total = await repo.list_paginated(
        page=1,
        page_size=20,
        enabled_only=True,
        business_week=True,
    )
    outside, outside_total = await repo.list_paginated(
        page=1,
        page_size=20,
        enabled_only=True,
        business_week=False,
    )

    assert this_week_total == 2
    assert {item.title for item in this_week} == {
        "本周发布但早先采集",
        "缺少发布日期且本周采集",
    }
    assert outside_total == 2
    assert {item.title for item in outside} == {
        "上周发布但本周补采",
        "本周范围结束后的公告",
    }


@pytest.mark.asyncio
async def test_notice_endpoint_forwards_new_optional_filters() -> None:
    class SpyNoticeService:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] = {}

        async def list_notices(self, **kwargs):
            self.kwargs = kwargs
            return PageData(items=[], total=0, page=1, page_size=20)

    service = SpyNoticeService()

    await list_notices_endpoint(
        page=1,
        page_size=20,
        keyword=None,
        category=None,
        review_status=None,
        archived=None,
        captured_today=True,
        business_today=True,
        business_week=True,
        month="2026-08",
        source_site="alpha.example",
        keyword_hit=True,
        high_priority=True,
        high_quality=True,
        project_signal="申报通知",
        service=service,
    )

    assert service.kwargs == {
        "page": 1,
        "page_size": 20,
        "keyword": None,
        "category": None,
        "review_status": None,
        "archived": None,
        "captured_today": True,
        "business_today": True,
        "business_week": True,
        "month": "2026-08",
        "source_site": "alpha.example",
        "keyword_hit": True,
        "high_priority": True,
        "high_quality": True,
            "project_signal": "申报通知",
            "focused_only": None,
            "user_id": None,
        }


def test_notice_endpoint_rejects_invalid_project_signal(
    asgi_test_client,
    auth_headers: dict[str, str],
) -> None:
    response = asgi_test_client.get(
        "/v1/notices",
        params={"project_signal": "invalid"},
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_notice_filters_are_optional_and_preserve_existing_list_behavior(async_session) -> None:
    service = await _seed_filter_rows(async_session)

    result = await service.list_notices(page=1, page_size=2)

    assert result.total == 5
    assert len(result.items) == 2
