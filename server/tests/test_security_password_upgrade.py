from app.core import security
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.schemas.auth import LoginPayload
from app.services.auth_service import AuthService


def test_legacy_password_hash_verifies_and_requests_upgrade() -> None:
    legacy_salt = bytes.fromhex("11" * 16)
    legacy_hash = security._derive_password_hash(  # type: ignore[attr-defined]
        "legacy-password",
        legacy_salt,
        iterations=100_000,
    )

    assert security.verify_password("legacy-password", legacy_salt.hex(), legacy_hash.hex())
    assert security.password_hash_needs_upgrade(legacy_salt.hex()) is True


def test_new_password_hash_encodes_cost_and_does_not_need_upgrade() -> None:
    password_hash, salt = security.hash_password("new-password")

    assert salt.startswith("pbkdf2_sha256$")
    assert security.verify_password("new-password", salt, password_hash)
    assert security.password_hash_needs_upgrade(salt) is False


@pytest.mark.asyncio
async def test_successful_login_upgrades_legacy_hash() -> None:
    legacy_salt = "22" * 16
    legacy_hash = security._derive_password_hash(  # type: ignore[attr-defined]
        "legacy-password",
        bytes.fromhex(legacy_salt),
        iterations=100_000,
    ).hex()
    user = SimpleNamespace(
        id=9,
        username="legacy-user",
        password_salt=legacy_salt,
        password_hash=legacy_hash,
        avatar_base64=None,
        role="user",
        is_active=True,
    )

    class FakeRepository:
        async def get_user_by_username(self, _username):
            return user

        async def update_user_password(self, current, *, password_hash, password_salt):
            current.password_hash = password_hash
            current.password_salt = password_salt
            return current

        async def create_session(self, current, _token_hash, expires_at):
            return SimpleNamespace(user_id=current.id, expires_at=expires_at)

    service = AuthService(FakeRepository())  # type: ignore[arg-type]
    service.settings.session_ttl_days = 7
    response = await service.login(
        LoginPayload(username="legacy-user", password="legacy-password")
    )

    assert response.user.id == 9
    assert user.password_salt.startswith("pbkdf2_sha256$")
    assert response.expires_at > datetime.now(UTC) + timedelta(days=6)
