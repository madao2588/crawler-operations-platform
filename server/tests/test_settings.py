from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.auth_service import AuthService


def test_cors_allowed_origins_list_parses_csv() -> None:
    settings = Settings(
        cors_allowed_origins="https://a.example, https://b.example ,,",
        cors_allowed_origin_regex=None,
    )

    assert settings.cors_allowed_origins_list == [
        "https://a.example",
        "https://b.example",
    ]


def test_bootstrap_admin_defaults_are_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRAWLER_BOOTSTRAP_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("CRAWLER_BOOTSTRAP_ADMIN_PASSWORD", raising=False)

    settings = Settings()

    assert settings.bootstrap_admin_username is None
    assert settings.bootstrap_admin_password is None


def test_requirement_one_government_hosts_bypass_system_proxy_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CRAWLER_OUTBOUND_NO_PROXY", raising=False)

    configured = {
        item.strip()
        for item in Settings().outbound_no_proxy.split(",")
        if item.strip()
    }

    assert {
        "service.most.gov.cn",
        "gdstc.gd.gov.cn",
        "kjj.gz.gov.cn",
        "www.hp.gov.cn",
        "www.hengqin.gov.cn",
        "kjt.hunan.gov.cn",
        "kjj.changsha.gov.cn",
    } <= configured


@pytest.mark.asyncio
async def test_bootstrap_admin_requires_both_values() -> None:
    service = AuthService(auth_repo=object())  # type: ignore[arg-type]
    service.settings = SimpleNamespace(
        bootstrap_admin_username="admin",
        bootstrap_admin_password=None,
        session_ttl_days=7,
    )

    with pytest.raises(
        ValueError,
        match="CRAWLER_BOOTSTRAP_ADMIN_USERNAME",
    ):
        await service.ensure_default_admin()


@pytest.mark.asyncio
async def test_bootstrap_admin_skips_when_both_values_are_unset() -> None:
    class RepoStub:
        def __init__(self) -> None:
            self.lookups: list[str] = []
            self.create_calls = 0

        async def get_user_by_username(self, username: str) -> None:
            self.lookups.append(username)
            return None

        async def create_user(self, **_: object) -> None:
            self.create_calls += 1

    repo = RepoStub()
    service = AuthService(auth_repo=repo)  # type: ignore[arg-type]
    service.settings = SimpleNamespace(
        bootstrap_admin_username=None,
        bootstrap_admin_password=None,
        session_ttl_days=7,
    )

    await service.ensure_default_admin()

    assert repo.lookups == []
    assert repo.create_calls == 0
