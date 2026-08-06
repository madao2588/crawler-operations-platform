import json
import uuid

from fastapi.testclient import TestClient


def test_template_create_update_use_delete_roundtrip(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client = asgi_test_client
    suffix = uuid.uuid4().hex[:10]
    template_id = f"pytest_template_{suffix}"

    created = client.post(
        "/v1/templates/tasks",
        headers=auth_headers,
        json={
            "id": template_id,
            "label": f"Pytest Template {suffix}",
            "name": "Pytest Template",
            "start_url": "https://example.com/template",
            "cron_expr": "0 * * * *",
            "parser_rules": None,
            "enabled": True,
            "description": "Template created by integration test.",
            "tags": ["pytest", "template"],
        },
    )
    assert created.status_code == 200
    created_data = created.json()["data"]
    assert created_data["id"] == template_id
    assert created_data["usage_count"] == 0
    assert created_data["last_used_at"] is None

    updated = client.put(
        f"/v1/templates/tasks/{template_id}",
        headers=auth_headers,
        json={
            "label": f"Updated Template {suffix}",
            "name": "Updated Pytest Template",
            "start_url": "https://example.com/template-updated",
            "cron_expr": "30 * * * *",
            "parser_rules": '{"title_selector":"h1"}',
            "enabled": False,
            "description": "Updated template description.",
            "tags": ["pytest", "updated"],
        },
    )
    assert updated.status_code == 200
    updated_data = updated.json()["data"]
    assert updated_data["id"] == template_id
    assert updated_data["usage_count"] == 0
    assert updated_data["last_used_at"] is None
    assert updated_data["enabled"] is False
    assert updated_data["tags"] == ["pytest", "updated"]

    tracked = client.post(
        f"/v1/templates/tasks/{template_id}/use",
        headers=auth_headers,
    )
    assert tracked.status_code == 200
    tracked_data = tracked.json()["data"]
    assert tracked_data["usage_count"] == 1
    assert tracked_data["last_used_at"] is not None

    deleted = client.delete(
        f"/v1/templates/tasks/{template_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 200

    listing = client.get("/v1/templates/tasks", headers=auth_headers)
    assert listing.status_code == 200
    ids = [item["id"] for item in listing.json()["data"]]
    assert template_id not in ids


def test_manual_source_collection_rejects_non_wechat_host(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    response = asgi_test_client.post(
        "/v1/templates/tasks/wechat_k_innovation/collect",
        headers=auth_headers,
        json={"url": "https://example.com/not-a-wechat-article"},
    )

    assert response.status_code == 400
    assert "mp.weixin.qq.com" in json.dumps(response.json(), ensure_ascii=False)
