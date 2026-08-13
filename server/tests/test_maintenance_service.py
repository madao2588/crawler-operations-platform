from datetime import UTC, datetime, timedelta
import os

from app.core.lifecycle import schedule_daily_maintenance
from app.services.maintenance_service import MaintenanceService


def test_cleanup_preserves_gitkeep_files(tmp_path) -> None:
    service = object.__new__(MaintenanceService)
    keep = tmp_path / ".gitkeep"
    expired = tmp_path / "old.csv"
    keep.write_text("", encoding="utf-8")
    expired.write_text("old", encoding="utf-8")
    old_timestamp = (datetime.now(UTC) - timedelta(days=40)).timestamp()
    os.utime(keep, (old_timestamp, old_timestamp))
    os.utime(expired, (old_timestamp, old_timestamp))

    deleted = service._delete_files_older_than(
        tmp_path,
        suffixes=None,
        older_than_days=30,
    )

    assert deleted == 1
    assert keep.exists()
    assert not expired.exists()


def test_schedule_daily_maintenance_uses_single_coalesced_job() -> None:
    calls: list[tuple[object, str, dict[str, object]]] = []

    class FakeScheduler:
        def add_job(self, function, trigger, **kwargs) -> None:  # noqa: ANN001
            calls.append((function, trigger, kwargs))

    schedule_daily_maintenance(FakeScheduler())  # type: ignore[arg-type]

    assert len(calls) == 1
    _, trigger, kwargs = calls[0]
    assert trigger == "cron"
    assert kwargs == {
        "hour": 3,
        "minute": 30,
        "timezone": "Asia/Shanghai",
        "id": "daily-maintenance",
        "replace_existing": True,
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 3600,
    }
