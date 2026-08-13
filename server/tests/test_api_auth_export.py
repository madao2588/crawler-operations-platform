"""Auth + CSV export routes (same app + DB as other HTTP smoke tests)."""

import base64
import os

from fastapi.testclient import TestClient


def test_login_success_and_me(
    asgi_test_client: TestClient,
    bootstrap_admin_credentials: tuple[str, str],
) -> None:
    client = asgi_test_client
    username, password = bootstrap_admin_credentials
    login = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    body = login.json()
    assert body.get("data") is not None
    token = body["data"]["access_token"]
    assert isinstance(token, str) and len(token) > 0

    me = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["data"]["user"]["username"] == username


def test_login_wrong_password_401(
    asgi_test_client: TestClient,
    bootstrap_admin_credentials: tuple[str, str],
) -> None:
    client = asgi_test_client
    username, _ = bootstrap_admin_credentials
    r = client.post(
        "/v1/auth/login",
        json={"username": username, "password": "wrong-password-xyz"},
    )
    assert r.status_code == 401
    payload = r.json()
    assert "message" in payload


def test_avatar_update_persists_across_login_and_can_be_cleared(
    asgi_test_client: TestClient,
    bootstrap_admin_credentials: tuple[str, str],
) -> None:
    client = asgi_test_client
    username, password = bootstrap_admin_credentials
    login = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    avatar = base64.b64encode(b"\x89PNG\r\n\x1a\naccount-avatar").decode("ascii")

    updated = client.patch(
        "/v1/auth/me/avatar",
        headers=headers,
        json={"avatar_base64": avatar},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["user"]["avatar_base64"] == avatar

    me = client.get("/v1/auth/me", headers=headers)
    assert me.json()["data"]["user"]["avatar_base64"] == avatar

    lean_me = client.get("/v1/auth/me?include_avatar=false", headers=headers)
    assert lean_me.status_code == 200
    assert lean_me.json()["data"]["user"]["avatar_base64"] is None

    relogin = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert relogin.json()["data"]["user"]["avatar_base64"] == avatar
    new_token = relogin.json()["data"]["access_token"]

    cleared = client.patch(
        "/v1/auth/me/avatar",
        headers={"Authorization": f"Bearer {new_token}"},
        json={"avatar_base64": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["user"]["avatar_base64"] is None


def test_avatar_update_rejects_unsupported_and_oversized_files(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    unsupported = base64.b64encode(b"not-an-image").decode("ascii")
    invalid_type = asgi_test_client.patch(
        "/v1/auth/me/avatar",
        headers=auth_headers,
        json={"avatar_base64": unsupported},
    )
    assert invalid_type.status_code == 422

    oversized = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"a" * (2 * 1024 * 1024)).decode("ascii")
    too_large = asgi_test_client.patch(
        "/v1/auth/me/avatar",
        headers=auth_headers,
        json={"avatar_base64": oversized},
    )
    assert too_large.status_code == 422


def test_login_uses_bootstrap_env_credentials(asgi_test_client: TestClient) -> None:
    client = asgi_test_client
    username = os.environ["CRAWLER_BOOTSTRAP_ADMIN_USERNAME"]
    password = os.environ["CRAWLER_BOOTSTRAP_ADMIN_PASSWORD"]

    ok = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert ok.status_code == 200

    assert (username, password) != ("madao", "1234")

    removed_default = client.post(
        "/v1/auth/login",
        json={"username": "madao", "password": "1234"},
    )
    assert removed_default.status_code == 401


def test_export_csv_utf8_bom_and_header(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client = asgi_test_client
    r = client.get("/v1/data/export/csv?limit=3", headers=auth_headers)
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "text/csv" in ct
    assert "attachment" in r.headers.get("content-disposition", "")
    raw = r.content
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"id" in raw[:120]
    assert b"task_id" in raw[:120]


def test_export_excel_compatible_information_pool(
    asgi_test_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    client = asgi_test_client
    r = client.get("/v1/data/export/excel?limit=3", headers=auth_headers)
    assert r.status_code == 200
    ct = r.headers.get("content-type", "")
    assert "application/vnd.ms-excel" in ct
    assert "attachment" in r.headers.get("content-disposition", "")
    text = r.content.decode("utf-8")
    assert "标题" in text
    assert "类别" in text
    assert "标记状态" in text
    assert "摘要" in text


def test_logout_invalidates_session_then_login_ok(
    asgi_test_client: TestClient,
    bootstrap_admin_credentials: tuple[str, str],
) -> None:
    client = asgi_test_client
    username, password = bootstrap_admin_credentials
    login = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    out = client.post("/v1/auth/logout", headers=headers)
    assert out.status_code == 200

    me = client.get("/v1/auth/me", headers=headers)
    assert me.status_code == 401

    login2 = client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login2.status_code == 200
    token2 = login2.json()["data"]["access_token"]
    assert isinstance(token2, str) and len(token2) > 0
    me2 = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token2}"})
    assert me2.status_code == 200
