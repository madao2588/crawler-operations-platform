import asyncio
import uuid

from fastapi.testclient import TestClient


async def _seed_notice() -> int:
    from app.core.database import AsyncSessionLocal
    from app.models.data import CollectedData
    from app.models.task import Task

    async with AsyncSessionLocal() as session:
        task = Task(
            name=f"Focus seed {uuid.uuid4().hex[:8]}",
            start_url=f"https://focus-seed.example/{uuid.uuid4().hex}",
            cron_expr="0 8 * * *",
            status=1,
        )
        session.add(task)
        await session.flush()
        row = CollectedData(
            task_id=task.id,
            title="用于个人关注测试的公告",
            content_text="项目申报信息",
            source_url=f"https://focus-seed.example/notice/{uuid.uuid4().hex}",
            quality_score=80,
            content_hash=f"focus-{uuid.uuid4().hex}",
            category="项目申报通知",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


def _create_user_and_login(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    username: str,
) -> dict[str, str]:
    password = "focus-password-123"
    created = client.post(
        "/v1/auth/users",
        headers=admin_headers,
        json={"username": username, "password": password, "role": "user"},
    )
    assert created.status_code == 200
    logged_in = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert logged_in.status_code == 200
    token = logged_in.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_personal_notice_focus_is_user_scoped(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    notice_id = asyncio.run(_seed_notice())
    first_user = _create_user_and_login(
        asgi_test_client,
        auth_headers,
        username="focus-user-a",
    )
    second_user = _create_user_and_login(
        asgi_test_client,
        auth_headers,
        username="focus-user-b",
    )

    focused = asgi_test_client.put(
        f"/v1/notices/{notice_id}/focus",
        headers=first_user,
    )
    assert focused.status_code == 200
    assert focused.json()["data"]["is_focused"] is True

    first_list = asgi_test_client.get(
        "/v1/notices?focused_only=true",
        headers=first_user,
    )
    second_list = asgi_test_client.get(
        "/v1/notices?focused_only=true",
        headers=second_user,
    )
    assert first_list.json()["data"]["total"] == 1
    assert first_list.json()["data"]["items"][0]["id"] == notice_id
    assert second_list.json()["data"]["total"] == 0

    removed = asgi_test_client.delete(
        f"/v1/notices/{notice_id}/focus",
        headers=first_user,
    )
    assert removed.status_code == 200
    assert removed.json()["data"]["is_focused"] is False
