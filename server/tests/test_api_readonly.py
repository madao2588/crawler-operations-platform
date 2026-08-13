"""Read-only v1 endpoints (shared session-scoped ASGI client)."""

import asyncio
import uuid

from fastapi.testclient import TestClient


async def _seed_notice_for_review() -> int:
    from app.core.database import AsyncSessionLocal
    from app.models.data import CollectedData
    from app.models.task import Task

    async with AsyncSessionLocal() as session:
        task = Task(
            name=f"Review seed {uuid.uuid4().hex[:8]}",
            start_url="https://seed.example",
            cron_expr="* * * * *",
            status=1,
        )
        session.add(task)
        await session.flush()
        row = CollectedData(
            task_id=task.id,
            title="脑胶质瘤竞品研发进展",
            content_html=None,
            content_text="用于测试新药部信息池人工标记和归档。",
            source_url=f"https://seed.example/{uuid.uuid4().hex}",
            snapshot_path=None,
            quality_score=80,
            content_hash=f"seed-{uuid.uuid4().hex}",
            category="竞品信息",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


def test_log_summary_shape(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    r = asgi_test_client.get("/v1/logs/summary", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    for key in (
        "total_logs",
        "info_logs",
        "warning_logs",
        "error_logs",
        "failed_task_count",
    ):
        assert key in data
        assert isinstance(data[key], int)


def test_logs_list_paginated(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    r = asgi_test_client.get(
        "/v1/logs",
        params={"page": 1, "page_size": 5},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
    if body["items"]:
        first = body["items"][0]
        assert "run_summary" in first


def test_logs_list_only_summary_filter(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    r = asgi_test_client.get(
        "/v1/logs",
        params={"page": 1, "page_size": 20, "only_summary": "true"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert "items" in body
    assert "total" in body
    for item in body["items"]:
        msg = (item.get("message") or "").lower()
        has_struct = item.get("run_summary") is not None
        looks_legacy_summary = (" summary:" in msg) or ("运行摘要" in msg)
        assert has_struct or looks_legacy_summary


def test_dashboard_overview_shape(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    r = asgi_test_client.get("/v1/dashboard/overview", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "metrics" in data
    assert "runtime" in data
    assert "high_value_notices" in data
    assert "recent_notices" in data
    rt = data["runtime"]
    assert rt["status"] in ("ok", "degraded")
    assert rt["database"] in ("ok", "error")


def test_keyword_rules_list(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    from app.utils.notice import DEFAULT_NOTICE_KEYWORDS, HIGH_PRIORITY_KEYWORDS

    r = asgi_test_client.get("/v1/keywords", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert "items" in data
    assert "total" in data
    assert data["default_total"] == len(DEFAULT_NOTICE_KEYWORDS)
    assert data["custom_total"] == data["total"] - data["default_total"]
    default_items = [item for item in data["items"] if item["is_default"]]
    assert {item["word"] for item in default_items} == set(DEFAULT_NOTICE_KEYWORDS)
    assert all(item["is_active"] for item in default_items)
    assert {item["word"] for item in default_items if item["is_high_priority"]} == set(HIGH_PRIORITY_KEYWORDS)


def test_task_templates_list(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    r = asgi_test_client.get("/v1/templates/tasks", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data, list)


def test_notices_list_paginated(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    r = asgi_test_client.get(
        "/v1/notices",
        params={"page": 1, "page_size": 10, "keyword": ""},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)


def test_notice_review_patch_updates_information_pool_metadata(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    notice_id = asyncio.run(_seed_notice_for_review())

    patched = asgi_test_client.patch(
        f"/v1/notices/{notice_id}/review",
        json={
            "review_status": "重点关注",
            "is_archived": True,
            "remark": "纳入新药部归档库",
        },
        headers=auth_headers,
    )
    assert patched.status_code == 200
    data = patched.json()["data"]
    assert data["review_status"] == "重点关注"
    assert data["is_archived"] is True
    assert data["remark"] == "纳入新药部归档库"

    focused = asgi_test_client.get(
        "/v1/notices",
        params={"review_status": "重点关注"},
        headers=auth_headers,
    )
    assert focused.status_code == 200
    assert notice_id in {item["id"] for item in focused.json()["data"]["items"]}


def test_stats_overview_shape(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    r = asgi_test_client.get("/v1/stats/overview", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    for key in (
        "total_tasks",
        "enabled_tasks",
        "total_data",
        "today_data",
        "total_logs",
        "avg_quality_score",
    ):
        assert key in data


def test_notice_detail_missing_returns_404(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    r = asgi_test_client.get("/v1/notices/999999999", headers=auth_headers)
    assert r.status_code == 404
    assert "message" in r.json()
