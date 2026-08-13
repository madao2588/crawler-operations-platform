from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.delivery_check import (  # noqa: E402
    EXPECTED_ENABLED_TASK_NAMES,
    audit_database,
    backup_database,
)

PROJECT_TASK_NAMES = EXPECTED_ENABLED_TASK_NAMES[:7]


def _create_delivery_database(
    path: Path,
    *,
    partial_task: str | None = None,
    partial_coverage_task: str | None = None,
) -> datetime:
    now = datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc)
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            status INTEGER NOT NULL,
            last_run_status TEXT,
            last_run_at DATETIME,
            last_success_at DATETIME,
            last_error_message TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE collected_data (
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL,
            title TEXT,
            content_text TEXT,
            source_url TEXT NOT NULL,
            category TEXT,
            metadata_json TEXT,
            fetch_time DATETIME,
            published_at DATETIME
        )
        """
    )
    for task_id, name in enumerate(EXPECTED_ENABLED_TASK_NAMES, start=1):
        is_partial = name == partial_task
        connection.execute(
            """
            INSERT INTO tasks (
                id, name, status, last_run_status, last_run_at,
                last_success_at, last_error_message
            ) VALUES (?, ?, 1, ?, ?, ?, ?)
            """,
            (
                task_id,
                name,
                "partial" if is_partial else "success",
                now.isoformat(),
                (now - timedelta(hours=1)).isoformat(),
                "请求超时" if is_partial else None,
            ),
        )
        if name not in PROJECT_TASK_NAMES:
            continue

        connection.execute(
            """
            INSERT INTO collected_data (
                task_id, title, content_text, source_url, category, metadata_json, fetch_time, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                "2026年度科技项目申报通知",
                "项目申报正在进行中",
                f"https://example.com/{task_id}/apply",
                "项目申报",
                '{"kind":"project_notice"}',
                now.isoformat(),
                now.isoformat(),
            ),
        )
        if name == partial_coverage_task:
            continue
        connection.execute(
            """
            INSERT INTO collected_data (
                task_id, title, content_text, source_url, category, metadata_json, fetch_time, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                "2026年度拟立项项目公示",
                "结果公示正在发布中",
                f"https://example.com/{task_id}/result",
                "项目申报",
                '{"kind":"project_notice"}',
                now.isoformat(),
                now.isoformat(),
            ),
        )
    connection.commit()
    connection.close()
    return now


def test_delivery_audit_accepts_all_twelve_fresh_successful_sources(tmp_path: Path) -> None:
    database = tmp_path / "data.db"
    now = _create_delivery_database(database)

    result = audit_database(database, now=now)

    assert result["status"] == "ok"
    assert result["expected_source_count"] == 12
    assert result["healthy_source_count"] == 12
    assert result["issues"] == []


def test_delivery_audit_reports_the_specific_unhealthy_source(tmp_path: Path) -> None:
    database = tmp_path / "data.db"
    failing_name = EXPECTED_ENABLED_TASK_NAMES[1]
    now = _create_delivery_database(database, partial_task=failing_name)

    result = audit_database(database, now=now)

    assert result["status"] == "failed"
    assert result["healthy_source_count"] == 11
    assert result["issues"] == [f"{failing_name}：最近运行状态为 partial；请求超时"]


def test_delivery_audit_reports_missing_result_publications_for_requirement_1_source(tmp_path: Path) -> None:
    database = tmp_path / "data.db"
    failing_name = PROJECT_TASK_NAMES[1]
    now = _create_delivery_database(database, partial_coverage_task=failing_name)

    result = audit_database(database, now=now)

    assert result["status"] == "failed"
    assert result["healthy_source_count"] == 11
    assert any(
        source["name"] == failing_name
        and source["status"] == "failed"
        and source["missing_signals"] == ["结果公示"]
        for source in result["sources"]
    )
    assert any("缺少结果公示" in issue for issue in result["issues"])


def test_delivery_audit_accepts_official_capability_evidence_for_unobserved_result(
    tmp_path: Path,
) -> None:
    database = tmp_path / "data.db"
    most_name = PROJECT_TASK_NAMES[0]
    now = _create_delivery_database(database, partial_coverage_task=most_name)

    result = audit_database(database, now=now)

    assert result["status"] == "ok"
    source = next(item for item in result["sources"] if item["name"] == most_name)
    assert source["status"] == "ok"
    assert source["unobserved_signals"] == ["结果公示"]
    assert source["missing_signals"] == []
    assert source["capability_evidence"]["结果公示"]["url"].startswith(
        "https://service.most.gov.cn/"
    )
    assert any("当前数据未检出结果公示" in warning for warning in result["warnings"])


def test_delivery_backup_uses_sqlite_online_backup_and_passes_integrity_check(tmp_path: Path) -> None:
    database = tmp_path / "data.db"
    now = _create_delivery_database(database)

    backup = backup_database(database, tmp_path / "backups", now=now)

    assert backup.exists()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 12
