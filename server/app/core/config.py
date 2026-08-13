from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "crawler_system"
    api_prefix: str = "/v1"
    database_url: str = "sqlite:///./data.db"
    max_retry: int = 3
    timeout: int = 30
    outbound_proxy_url: str | None = None
    use_system_proxy: bool = True
    outbound_no_proxy: str = (
        "localhost,127.0.0.1,::1,"
        "service.most.gov.cn,gdstc.gd.gov.cn,kjj.gz.gov.cn,"
        "www.hp.gov.cn,www.hengqin.gov.cn,kjt.hunan.gov.cn,"
        "kjj.changsha.gov.cn"
    )
    task_stale_minutes: int = 30
    startup_catch_up_enabled: bool = True
    snapshot_dir: str = "storage/snapshots"
    export_dir: str = "storage/exports"
    bootstrap_admin_username: str | None = None
    bootstrap_admin_password: str | None = None
    session_ttl_days: int = 7
    maintenance_enabled: bool = True
    maintenance_backup_dir: str = "backups/runtime"
    maintenance_backup_retention_days: int = 14
    maintenance_manifest_retention_days: int = 14
    maintenance_export_retention_days: int = 30
    maintenance_log_retention_days: int = 90
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_minutes: int = 15
    login_rate_limit_block_minutes: int = 15
    cors_allowed_origins: str = (
        "http://127.0.0.1:3000,"
        "http://localhost:3000,"
        "http://127.0.0.1:3010,"
        "http://localhost:3010"
    )
    cors_allowed_origin_regex: str | None = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_prefix="CRAWLER_",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
