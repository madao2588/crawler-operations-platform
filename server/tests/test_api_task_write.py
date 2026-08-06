"""Task create / read / delete via HTTP (shared ASGI client)."""

import asyncio
import sqlite3
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import app.engine.pipeline as pipeline_mod
from fastapi.testclient import TestClient


def test_create_task_get_and_delete(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    client = asgi_test_client
    headers = auth_headers
    suffix = uuid.uuid4().hex[:10]
    name = f"pytest_task_{suffix}"
    body = {
        "name": name,
        "start_url": "https://example.com/pytest-task",
        "cron_expr": "0 0 * * *",
        "status": 1,
        "parser_rules": None,
    }
    created = client.post("/v1/tasks", json=body, headers=headers)
    assert created.status_code == 200
    payload = created.json()
    assert payload.get("data") is not None
    data = payload["data"]
    assert data["name"] == name
    assert data["start_url"] == body["start_url"]
    task_id = data["id"]
    assert isinstance(task_id, int) and task_id > 0

    fetched = client.get(f"/v1/tasks/{task_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == task_id
    assert fetched.json()["data"]["name"] == name

    deleted = client.delete(f"/v1/tasks/{task_id}", headers=headers)
    assert deleted.status_code == 200

    missing = client.get(f"/v1/tasks/{task_id}", headers=headers)
    assert missing.status_code == 404


def test_put_task_update_name(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    client = asgi_test_client
    headers = auth_headers
    suffix = uuid.uuid4().hex[:10]
    name = f"pytest_put_{suffix}"
    created = client.post(
        "/v1/tasks",
        json={
            "name": name,
            "start_url": "https://example.com/put",
            "cron_expr": "0 0 * * *",
            "status": 1,
        },
        headers=headers,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]
    updated_name = f"{name}_renamed"
    put = client.put(
        f"/v1/tasks/{task_id}",
        json={"name": updated_name},
        headers=headers,
    )
    assert put.status_code == 200
    assert put.json()["data"]["name"] == updated_name
    assert client.get(f"/v1/tasks/{task_id}", headers=headers).json()["data"]["name"] == updated_name
    assert client.delete(f"/v1/tasks/{task_id}", headers=headers).status_code == 200


async def _slow_pipeline_run(_task_id: int) -> None:
    await asyncio.sleep(1.0)


async def _instant_pipeline_run(_task_id: int) -> None:
    return


def test_post_run_task_returns_queued(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    monkeypatch.setattr(pipeline_mod, "run_task", _instant_pipeline_run)
    client = asgi_test_client
    headers = auth_headers
    suffix = uuid.uuid4().hex[:10]
    name = f"pytest_run_{suffix}"
    created = client.post(
        "/v1/tasks",
        json={
            "name": name,
            "start_url": "https://example.com/run",
            "cron_expr": "0 0 * * *",
            "status": 1,
        },
        headers=headers,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]
    run = client.post(f"/v1/tasks/{task_id}/run", headers=headers)
    assert run.status_code == 200
    payload = run.json()["data"]
    assert payload["task_id"] == task_id
    assert payload["status"] == "queued"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        status = client.get(f"/v1/tasks/{task_id}", headers=headers).json()["data"]["last_run_status"]
        if status not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert client.delete(f"/v1/tasks/{task_id}", headers=headers).status_code == 200


def test_post_run_enabled_queues_enabled_tasks(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    monkeypatch.setattr(pipeline_mod, "run_task", _instant_pipeline_run)
    client = asgi_test_client
    headers = auth_headers
    suffix = uuid.uuid4().hex[:10]
    created = client.post(
        "/v1/tasks",
        json={
            "name": f"pytest_run_enabled_{suffix}",
            "start_url": "https://example.com/run-enabled",
            "cron_expr": "0 0 * * *",
            "status": 1,
        },
        headers=headers,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]
    r = client.post("/v1/tasks/run-enabled", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data["queued_task_ids"], list)
    assert isinstance(data["skipped_task_ids"], list)
    assert isinstance(data["errors"], list)
    assert task_id in data["queued_task_ids"] or task_id in data["skipped_task_ids"]
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        status = client.get(f"/v1/tasks/{task_id}", headers=headers).json()["data"]["last_run_status"]
        if status not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert client.delete(f"/v1/tasks/{task_id}", headers=headers).status_code == 200


def test_post_run_enabled_retries_failed_enabled_tasks(
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
            "name": f"pytest_quarantine_{suffix}",
            "start_url": "https://example.com/quarantine",
            "cron_expr": "0 0 * * *",
            "status": 1,
        },
        headers=auth_headers,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]

    with sqlite3.connect(test_database_path) as conn:
        conn.execute(
            """
            update tasks
               set last_run_status = ?,
                   last_error_message = ?
             where id = ?
            """,
            ("failed", "source timeout", task_id),
        )
        conn.commit()

    r = client.post("/v1/tasks/run-enabled", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["quarantined_task_ids"] == []
    assert task_id in data["queued_task_ids"]

    fetched = client.get(f"/v1/tasks/{task_id}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["status"] == 1

    for _ in range(100):
        run_status = client.get(
            f"/v1/tasks/{task_id}",
            headers=auth_headers,
        ).json()["data"]["last_run_status"]
        if run_status not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert client.delete(f"/v1/tasks/{task_id}", headers=auth_headers).status_code == 200


def test_delete_task_rejected_while_queued_or_running(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    monkeypatch.setattr(pipeline_mod, "run_task", _slow_pipeline_run)
    client = asgi_test_client
    headers = auth_headers
    suffix = uuid.uuid4().hex[:10]
    name = f"pytest_del_{suffix}"
    created = client.post(
        "/v1/tasks",
        json={
            "name": name,
            "start_url": "https://example.com/delbusy",
            "cron_expr": "0 0 * * *",
            "status": 1,
        },
        headers=headers,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]
    assert client.post(f"/v1/tasks/{task_id}/run", headers=headers).status_code == 200
    assert client.delete(f"/v1/tasks/{task_id}", headers=headers).status_code == 409
    time.sleep(1.2)
    assert client.delete(f"/v1/tasks/{task_id}", headers=headers).status_code == 200


def test_post_run_task_conflict_409_while_active(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    monkeypatch.setattr(pipeline_mod, "run_task", _slow_pipeline_run)
    client = asgi_test_client
    headers = auth_headers
    suffix = uuid.uuid4().hex[:10]
    name = f"pytest_run2_{suffix}"
    created = client.post(
        "/v1/tasks",
        json={
            "name": name,
            "start_url": "https://example.com/run2",
            "cron_expr": "0 0 * * *",
            "status": 1,
        },
        headers=headers,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]
    first = client.post(f"/v1/tasks/{task_id}/run", headers=headers)
    assert first.status_code == 200
    second = client.post(f"/v1/tasks/{task_id}/run", headers=headers)
    assert second.status_code == 409
    time.sleep(1.2)
    assert client.delete(f"/v1/tasks/{task_id}", headers=headers).status_code == 200


def test_post_run_task_recovers_stale_running_state(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
    test_database_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(pipeline_mod, "run_task", _instant_pipeline_run)
    client = asgi_test_client
    headers = auth_headers
    suffix = uuid.uuid4().hex[:10]
    created = client.post(
        "/v1/tasks",
        json={
            "name": f"pytest_stale_{suffix}",
            "start_url": "https://example.com/stale",
            "cron_expr": "0 0 * * *",
            "status": 1,
        },
        headers=headers,
    )
    assert created.status_code == 200
    task_id = created.json()["data"]["id"]

    stale_run_at = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    with sqlite3.connect(test_database_path) as conn:
        conn.execute(
            """
            update tasks
               set last_run_status = ?,
                   last_run_at = ?,
                   last_error_message = ?
             where id = ?
            """,
            ("running", stale_run_at, None, task_id),
        )
        conn.commit()

    run = client.post(f"/v1/tasks/{task_id}/run", headers=headers)
    assert run.status_code == 200
    payload = run.json()["data"]
    assert payload["task_id"] == task_id
    assert payload["status"] == "queued"
    assert payload["recovered_stale_run"] is True

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        status = client.get(f"/v1/tasks/{task_id}", headers=headers).json()["data"]["last_run_status"]
        if status not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert client.delete(f"/v1/tasks/{task_id}", headers=headers).status_code == 200


def test_create_task_parser_rules_invalid_json_rejected(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client = asgi_test_client
    suffix = uuid.uuid4().hex[:10]
    r = client.post(
        "/v1/tasks",
        json={
            "name": f"pytest_badjson_{suffix}",
            "start_url": "https://example.com/badjson",
            "cron_expr": "0 0 * * *",
            "status": 1,
            "parser_rules": "{",
        },
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_create_task_parser_rules_array_root_rejected(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client = asgi_test_client
    suffix = uuid.uuid4().hex[:10]
    r = client.post(
        "/v1/tasks",
        json={
            "name": f"pytest_arr_{suffix}",
            "start_url": "https://example.com/arr",
            "cron_expr": "0 0 * * *",
            "status": 1,
            "parser_rules": "[1]",
        },
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_create_task_parser_rules_too_long_rejected(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client = asgi_test_client
    suffix = uuid.uuid4().hex[:10]
    huge = "x" * 200_000
    r = client.post(
        "/v1/tasks",
        json={
            "name": f"pytest_big_{suffix}",
            "start_url": "https://example.com/big",
            "cron_expr": "0 0 * * *",
            "status": 1,
            "parser_rules": huge,
        },
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_list_data_paginated(asgi_test_client: TestClient, auth_headers: dict[str, str]) -> None:
    client = asgi_test_client
    r = client.get("/v1/data", params={"page": 1, "page_size": 5}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()["data"]
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
