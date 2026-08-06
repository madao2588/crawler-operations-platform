from datetime import datetime, timezone

import pytest

from app.models.data import CollectedData
from app.models.task import Task
from app.repositories.data_repo import DataRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.services.notice_service import NoticeService


UTC = timezone.utc


async def _seed_month_rows(async_session) -> NoticeService:
    alpha = Task(
        name="月份筛选测试来源采集",
        start_url="https://alpha.example/root",
        cron_expr="0 8 * * *",
        status=1,
    )
    beta = Task(
        name="另一个月份筛选来源采集",
        start_url="https://beta.example/root",
        cron_expr="0 8 * * *",
        status=1,
    )
    async_session.add_all([alpha, beta])
    await async_session.flush()

    async_session.add_all(
        [
            CollectedData(
                task_id=alpha.id,
                title="发布日期落在七月的公告",
                content_text="网站发布日期优先于八月采集时间",
                source_url="https://alpha.example/notices/published-july",
                quality_score=70,
                content_hash="month-published-july",
                category="未分类",
                published_at=datetime(2026, 6, 30, 16, 0, tzinfo=UTC),
                fetch_time=datetime(2026, 7, 5, 2, 0, tzinfo=UTC),
            ),
            CollectedData(
                task_id=alpha.id,
                title="缺少发布日期的八月公告",
                content_text="缺少发布日期时使用采集时间",
                source_url="https://alpha.example/notices/captured-august",
                quality_score=70,
                content_hash="month-captured-august",
                category="未分类",
                published_at=None,
                fetch_time=datetime(2026, 7, 31, 16, 0, tzinfo=UTC),
            ),
            CollectedData(
                task_id=alpha.id,
                title="上海时区七月末公告",
                content_text="UTC 时间仍需按上海自然月归类",
                source_url="https://alpha.example/notices/july-boundary",
                quality_score=70,
                content_hash="month-july-boundary",
                category="未分类",
                published_at=datetime(2026, 7, 31, 15, 59, 59, tzinfo=UTC),
                fetch_time=datetime(2026, 7, 31, 16, 1, tzinfo=UTC),
            ),
            CollectedData(
                task_id=beta.id,
                title="另一个来源的八月公告",
                content_text="用于验证月份和来源组合筛选",
                source_url="https://beta.example/notices/august",
                quality_score=70,
                content_hash="month-beta-august",
                category="未分类",
                published_at=datetime(2026, 8, 10, 1, 0, tzinfo=UTC),
                fetch_time=datetime(2026, 8, 10, 2, 0, tzinfo=UTC),
            ),
        ]
    )
    await async_session.commit()
    return NoticeService(
        data_repo=DataRepository(async_session),
        keyword_repo=KeywordRepository(async_session),
    )


@pytest.mark.asyncio
async def test_notice_month_filter_prefers_published_date_and_falls_back_to_capture_date(
    async_session,
) -> None:
    service = await _seed_month_rows(async_session)

    july = await service.list_notices(page=1, page_size=20, month="2026-07")
    august = await service.list_notices(page=1, page_size=20, month="2026-08")

    assert {item.title for item in july.items} == {
        "发布日期落在七月的公告",
        "上海时区七月末公告",
    }
    assert {item.title for item in august.items} == {
        "缺少发布日期的八月公告",
        "另一个来源的八月公告",
    }


@pytest.mark.asyncio
async def test_notice_month_options_match_combined_filters(async_session) -> None:
    service = await _seed_month_rows(async_session)

    all_months = await service.list_months()
    alpha_months = await service.list_months(source_site="alpha.example")

    assert [(item.month, item.count) for item in all_months] == [
        ("2026-08", 2),
        ("2026-07", 2),
    ]
    assert [(item.month, item.count) for item in alpha_months] == [
        ("2026-08", 1),
        ("2026-07", 2),
    ]


def test_notice_month_endpoint_returns_options(
    asgi_test_client,
    auth_headers: dict[str, str],
) -> None:
    response = asgi_test_client.get(
        "/v1/notices/months",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_notice_endpoint_rejects_invalid_month(
    asgi_test_client,
    auth_headers: dict[str, str],
) -> None:
    response = asgi_test_client.get(
        "/v1/notices",
        params={"month": "2026-13"},
        headers=auth_headers,
    )

    assert response.status_code == 422
