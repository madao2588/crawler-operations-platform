"""Same-URL re-crawls should only update visible collection time when content changes."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.engine import pipeline as pipeline_mod
from app.models.data import CollectedData
from app.models.task import Task
from app.repositories.data_repo import DataRepository
from app.repositories.log_repo import LogRepository
from app.schemas.task import TaskStatus
from app.utils.hash import sha256_text


@pytest.mark.asyncio
async def test_same_url_recollect_skips_update_when_hash_unchanged(
    async_session, monkeypatch
) -> None:
    async_session.add(
        Task(
            name="T1",
            start_url="https://a.example",
            cron_expr="* * * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.flush()
    task_id = (await async_session.execute(select(Task.id))).scalar_one()
    page_url = "https://a.example/page"
    body = "hello"
    content_hash = sha256_text(body)
    old_ft = datetime.now(timezone.utc) - timedelta(days=30)

    row = CollectedData(
        task_id=task_id,
        title="Old",
        content_html="<p>hello</p>",
        content_text=body,
        source_url=page_url,
        snapshot_path=None,
        quality_score=40,
        content_hash=content_hash,
    )
    async_session.add(row)
    await async_session.flush()
    row.fetch_time = old_ft
    await async_session.commit()

    async def fake_download(**_kwargs) -> str:
        return "<html/>"

    async def fake_parse(_html: str, **_kwargs) -> dict:
        return {"content_html": "<p>hello</p>", "title": "t"}

    monkeypatch.setattr(pipeline_mod, "_download_page", fake_download)
    monkeypatch.setattr(pipeline_mod, "_parse_page", fake_parse)
    monkeypatch.setattr(pipeline_mod, "save_snapshot", lambda **kwargs: "snap/x.html")

    log_repo = LogRepository(async_session)
    data_repo = DataRepository(async_session)
    result = await pipeline_mod._collect_and_store_one(
        task_id=task_id,
        run_id="test-run",
        page_url=page_url,
        parser_rules=None,
        log_repo=log_repo,
        data_repo=data_repo,
        crawl_rules=None,
    )
    assert result == "skipped_hash"

    await async_session.refresh(row)
    new_ft = row.fetch_time
    if new_ft.tzinfo is None:
        new_ft = new_ft.replace(tzinfo=timezone.utc)
    assert new_ft == old_ft


@pytest.mark.asyncio
async def test_same_url_recollect_updates_generic_title_without_touching_fetch_time(
    async_session, monkeypatch
) -> None:
    async_session.add(
        Task(
            name="T1",
            start_url="https://service.most.gov.cn/xmtj/",
            cron_expr="* * * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.flush()
    task_id = (await async_session.execute(select(Task.id))).scalar_one()
    page_url = "https://service.most.gov.cn/kjjh_tztg_all/20230913/5373.html"
    body = "各有关单位：按照科技部关于国家重点研发计划重点专项评审立项的总体要求和部署。"
    old_ft = datetime.now(timezone.utc) - timedelta(days=30)

    row = CollectedData(
        task_id=task_id,
        title="国家科技管理信息系统公共服务平台",
        content_html=f"<p>{body}</p>",
        content_text=body,
        source_url=page_url,
        snapshot_path=None,
        quality_score=100,
        content_hash=sha256_text(body),
        ai_summary="旧摘要",
    )
    async_session.add(row)
    await async_session.flush()
    row.fetch_time = old_ft
    await async_session.commit()

    async def fake_download(**_kwargs) -> str:
        return "<html/>"

    async def fake_parse(_html: str, **_kwargs) -> dict:
        return {
            "content_html": f"<p>{body}</p>",
            "title": "国家科技管理信息系统公共服务平台",
        }

    monkeypatch.setattr(pipeline_mod, "_download_page", fake_download)
    monkeypatch.setattr(pipeline_mod, "_parse_page", fake_parse)

    log_repo = LogRepository(async_session)
    data_repo = DataRepository(async_session)
    result = await pipeline_mod._collect_and_store_one(
        task_id=task_id,
        run_id="test-run",
        page_url=page_url,
        parser_rules=None,
        log_repo=log_repo,
        data_repo=data_repo,
        crawl_rules=None,
        fallback_title="关于组织申报重点专项的通知",
    )
    assert result == "skipped_hash"

    await async_session.refresh(row)
    new_ft = row.fetch_time
    if new_ft.tzinfo is None:
        new_ft = new_ft.replace(tzinfo=timezone.utc)
    assert new_ft == old_ft
    assert row.title == "关于组织申报重点专项的通知"


@pytest.mark.asyncio
async def test_same_url_recollect_backfills_published_at_without_touching_fetch_time(
    async_session, monkeypatch
) -> None:
    async_session.add(
        Task(
            name="T1",
            start_url="https://gov.example/notices",
            cron_expr="* * * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.flush()
    task_id = (await async_session.execute(select(Task.id))).scalar_one()
    page_url = "https://gov.example/notices/1.html"
    body = "关于组织申报重点专项的正文内容。"
    old_ft = datetime.now(timezone.utc) - timedelta(days=30)

    row = CollectedData(
        task_id=task_id,
        title="关于组织申报重点专项的通知",
        content_html=f"<p>{body}</p>",
        content_text=body,
        source_url=page_url,
        snapshot_path=None,
        quality_score=80,
        content_hash=sha256_text(body),
    )
    async_session.add(row)
    await async_session.flush()
    row.fetch_time = old_ft
    await async_session.commit()

    async def fake_download(**_kwargs) -> str:
        return "<html/>"

    async def fake_parse(_html: str, **_kwargs) -> dict:
        return {
            "content_html": f"<p>{body}</p>",
            "title": "关于组织申报重点专项的通知",
            "published_at": "发布时间：2026年07月21日",
        }

    monkeypatch.setattr(pipeline_mod, "_download_page", fake_download)
    monkeypatch.setattr(pipeline_mod, "_parse_page", fake_parse)

    result = await pipeline_mod._collect_and_store_one(
        task_id=task_id,
        run_id="test-run",
        page_url=page_url,
        parser_rules=None,
        log_repo=LogRepository(async_session),
        data_repo=DataRepository(async_session),
        crawl_rules=None,
    )

    assert result == "skipped_hash"
    await async_session.refresh(row)
    stored_fetch_time = row.fetch_time
    if stored_fetch_time.tzinfo is None:
        stored_fetch_time = stored_fetch_time.replace(tzinfo=timezone.utc)
    assert stored_fetch_time == old_ft
    stored_published_at = row.published_at
    if stored_published_at is not None and stored_published_at.tzinfo is None:
        stored_published_at = stored_published_at.replace(tzinfo=timezone.utc)
    assert stored_published_at == datetime(2026, 7, 20, 16, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_same_url_recollect_updates_fetch_time_when_content_changes(
    async_session, monkeypatch
) -> None:
    async_session.add(
        Task(
            name="T1",
            start_url="https://a.example",
            cron_expr="* * * * *",
            status=int(TaskStatus.ENABLED),
        )
    )
    await async_session.flush()
    task_id = (await async_session.execute(select(Task.id))).scalar_one()
    page_url = "https://a.example/page"
    old_body = "hello"
    old_ft = datetime.now(timezone.utc) - timedelta(days=30)

    row = CollectedData(
        task_id=task_id,
        title="Old",
        content_html="<p>hello</p>",
        content_text=old_body,
        source_url=page_url,
        snapshot_path=None,
        quality_score=40,
        content_hash=sha256_text(old_body),
    )
    async_session.add(row)
    await async_session.flush()
    row.fetch_time = old_ft
    await async_session.commit()

    async def fake_download(**_kwargs) -> str:
        return "<html/>"

    async def fake_parse(_html: str, **_kwargs) -> dict:
        return {"content_html": "<p>changed</p>", "title": "Updated"}

    monkeypatch.setattr(pipeline_mod, "_download_page", fake_download)
    monkeypatch.setattr(pipeline_mod, "_parse_page", fake_parse)
    monkeypatch.setattr(pipeline_mod, "save_snapshot", lambda **kwargs: "snap/x.html")

    log_repo = LogRepository(async_session)
    data_repo = DataRepository(async_session)
    result = await pipeline_mod._collect_and_store_one(
        task_id=task_id,
        run_id="test-run",
        page_url=page_url,
        parser_rules=None,
        log_repo=log_repo,
        data_repo=data_repo,
        crawl_rules=None,
    )
    assert result == "stored"

    await async_session.refresh(row)
    new_ft = row.fetch_time
    if new_ft.tzinfo is None:
        new_ft = new_ft.replace(tzinfo=timezone.utc)
    assert new_ft > old_ft
    assert row.title == "Updated"
    assert row.content_hash == sha256_text("changed")
