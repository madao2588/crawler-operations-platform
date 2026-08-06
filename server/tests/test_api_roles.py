"""Two-role authentication and authorization boundaries."""

from uuid import uuid4

from fastapi.testclient import TestClient


def _create_user(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    password: str = "user-password-123",
    role: str = "user",
) -> tuple[dict, str]:
    username = f"user_{uuid4().hex[:10]}"
    response = client.post(
        "/v1/auth/users",
        headers=admin_headers,
        json={"username": username, "password": password, "role": role},
    )
    assert response.status_code == 200
    return response.json()["data"], password


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_bootstrap_account_is_admin_and_can_manage_users(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    me = asgi_test_client.get("/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["data"]["user"]["role"] == "admin"
    assert me.json()["data"]["user"]["is_active"] is True

    created, _ = _create_user(asgi_test_client, auth_headers)
    assert created["role"] == "user"
    assert created["is_active"] is True

    listed = asgi_test_client.get("/v1/auth/users", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["id"] == created["id"] for item in listed.json()["data"])


def test_regular_user_can_read_but_all_business_writes_are_forbidden(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    user, password = _create_user(asgi_test_client, auth_headers)
    user_headers = _login(asgi_test_client, user["username"], password)

    for path in ("/v1/notices?page=1&page_size=1", "/v1/tasks?page=1&page_size=1", "/v1/keywords"):
        assert asgi_test_client.get(path, headers=user_headers).status_code == 200

    forbidden_requests = (
        ("post", "/v1/tasks/run-enabled", None),
        (
            "post",
            "/v1/keywords",
            {"word": f"blocked-{uuid4().hex[:8]}", "is_active": True},
        ),
        (
            "post",
            "/v1/templates/test",
            {"start_url": "https://example.com", "parser_rules": "{}"},
        ),
        (
            "patch",
            "/v1/notices/1/review",
            {"review_status": "已关注"},
        ),
    )
    for method, path, payload in forbidden_requests:
        response = asgi_test_client.request(method, path, headers=user_headers, json=payload)
        assert response.status_code == 403, (method, path, response.text)

    assert asgi_test_client.get("/v1/auth/users", headers=user_headers).status_code == 403


def test_user_can_change_own_password_and_admin_can_reset_it(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    user, original_password = _create_user(asgi_test_client, auth_headers)
    user_headers = _login(asgi_test_client, user["username"], original_password)

    wrong_current = asgi_test_client.patch(
        "/v1/auth/me/password",
        headers=user_headers,
        json={"current_password": "wrong-current", "new_password": "new-password-123"},
    )
    assert wrong_current.status_code == 400

    changed = asgi_test_client.patch(
        "/v1/auth/me/password",
        headers=user_headers,
        json={"current_password": original_password, "new_password": "new-password-123"},
    )
    assert changed.status_code == 200
    assert asgi_test_client.post(
        "/v1/auth/login",
        json={"username": user["username"], "password": original_password},
    ).status_code == 401
    _login(asgi_test_client, user["username"], "new-password-123")

    reset = asgi_test_client.post(
        f"/v1/auth/users/{user['id']}/reset-password",
        headers=auth_headers,
        json={"new_password": "reset-password-123"},
    )
    assert reset.status_code == 200
    assert asgi_test_client.post(
        "/v1/auth/login",
        json={"username": user["username"], "password": "new-password-123"},
    ).status_code == 401
    _login(asgi_test_client, user["username"], "reset-password-123")


def test_disabling_user_revokes_sessions_and_admin_cannot_disable_self(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
    bootstrap_admin_credentials: tuple[str, str],
) -> None:
    user, password = _create_user(asgi_test_client, auth_headers)
    user_headers = _login(asgi_test_client, user["username"], password)

    disabled = asgi_test_client.patch(
        f"/v1/auth/users/{user['id']}/status",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["is_active"] is False
    assert asgi_test_client.get("/v1/auth/me", headers=user_headers).status_code == 401
    assert asgi_test_client.post(
        "/v1/auth/login",
        json={"username": user["username"], "password": password},
    ).status_code == 401

    admin_username, _ = bootstrap_admin_credentials
    users = asgi_test_client.get("/v1/auth/users", headers=auth_headers).json()["data"]
    admin = next(item for item in users if item["username"] == admin_username)
    self_disable = asgi_test_client.patch(
        f"/v1/auth/users/{admin['id']}/status",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert self_disable.status_code == 400
