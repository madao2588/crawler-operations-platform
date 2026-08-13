from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.services.template_service import (
    NEW_DRUG_SOURCE_TEMPLATES,
    PROJECT_SIGNAL_CAPABILITY_EVIDENCE,
)
from app.utils.notice import project_notice_kind

DEFAULT_DATABASE = REPO_ROOT / "server" / "data.db"
DEFAULT_BACKUP_DIR = REPO_ROOT / "backups"
DEFAULT_REPORT = REPO_ROOT / "artifacts" / "delivery-check-latest.json"

EXPECTED_ENABLED_TASK_NAMES = (
    "科技部项目申报与结果公示采集",
    "广东省科技厅项目申报与结果公示采集",
    "广州市科技局项目申报与结果公示采集",
    "黄埔区科技局项目申报与结果公示采集",
    "横琴项目申报与结果公示采集",
    "湖南省科技厅项目申报与结果公示采集",
    "长沙市科技局项目申报与结果公示采集",
    "中国药学会会议资讯采集",
    "生物谷会议采集",
    "CPHI China 行业会议采集",
    "PubMed 竞品文献入口",
    "ClinicalTrials.gov 竞品临床试验采集",
)
REQUIREMENT_1_TASK_NAMES = EXPECTED_ENABLED_TASK_NAMES[:7]
REQUIRED_PROJECT_SIGNAL_LABELS = ("申报通知", "结果公示")
PROJECT_SOURCE_ID_BY_TASK_NAME = {
    str(template["name"]): str(template["id"])
    for template in NEW_DRUG_SOURCE_TEMPLATES
    if str(template["name"]) in REQUIREMENT_1_TASK_NAMES
}


def audit_database(
    database: Path,
    *,
    now: datetime | None = None,
    stale_after: timedelta = timedelta(hours=24),
) -> dict[str, Any]:
    checked_at = now or datetime.now(timezone.utc)
    with sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, name, status, last_run_status, last_run_at,
                   last_success_at, last_error_message
            FROM tasks
            ORDER BY id
            """
        ).fetchall()
        signal_rows = connection.execute(
            """
            SELECT task_id, title, content_text, category, metadata_json
            FROM collected_data
            WHERE task_id IN (
                SELECT id FROM tasks WHERE name IN ({placeholders})
            )
            """.format(placeholders=", ".join("?" for _ in REQUIREMENT_1_TASK_NAMES)),
            REQUIREMENT_1_TASK_NAMES,
        ).fetchall()

    by_name = {str(row["name"]): row for row in rows}
    signal_counts_by_task = _collect_project_signal_counts(signal_rows)
    sources: list[dict[str, Any]] = []
    issues: list[str] = []
    warnings: list[str] = []
    healthy_count = 0
    for name in EXPECTED_ENABLED_TASK_NAMES:
        row = by_name.get(name)
        source: dict[str, Any] = {"name": name, "status": "failed"}
        if row is None:
            source["reason"] = "任务不存在"
            issues.append(f"{name}：任务不存在")
            sources.append(source)
            continue

        source.update(
            {
                "task_id": int(row["id"]),
                "enabled": int(row["status"]) == 1,
                "last_run_status": row["last_run_status"],
                "last_run_at": row["last_run_at"],
                "last_success_at": row["last_success_at"],
                "last_error_message": row["last_error_message"],
            }
        )
        reasons: list[str] = []
        signal_counts = signal_counts_by_task.get(
            int(row["id"]),
            {label: 0 for label in REQUIRED_PROJECT_SIGNAL_LABELS},
        )
        if name in REQUIREMENT_1_TASK_NAMES:
            source["signal_counts"] = signal_counts
            unobserved_signals = [
                label for label in REQUIRED_PROJECT_SIGNAL_LABELS if signal_counts[label] == 0
            ]
            source_id = PROJECT_SOURCE_ID_BY_TASK_NAME.get(name, "")
            configured_evidence = PROJECT_SIGNAL_CAPABILITY_EVIDENCE.get(source_id, {})
            capability_evidence = {
                label: configured_evidence[label]
                for label in unobserved_signals
                if label in configured_evidence
            }
            missing_signals = [
                label for label in unobserved_signals if label not in capability_evidence
            ]
            source["unobserved_signals"] = unobserved_signals
            source["capability_evidence"] = capability_evidence
            source["missing_signals"] = missing_signals
            if unobserved_signals and not missing_signals:
                warnings.append(
                    f"{name}：当前数据未检出{'、'.join(unobserved_signals)}；"
                    "采集能力已由同一官方来源的历史公告与回归测试验证"
                )
        else:
            missing_signals = []
        if int(row["status"]) != 1:
            reasons.append("任务未启用")
        run_status = str(row["last_run_status"] or "never")
        if run_status != "success":
            reasons.append(f"最近运行状态为 {run_status}")
        last_success = _parse_database_datetime(row["last_success_at"])
        if last_success is None:
            reasons.append("没有成功采集记录")
        elif last_success < checked_at - stale_after:
            reasons.append("超过 24 小时未成功更新")
        error_message = str(row["last_error_message"] or "").strip()
        if error_message and run_status != "success":
            reasons.append(error_message)
        if missing_signals:
            reasons.append(f"缺少{'、'.join(missing_signals)}")

        if reasons:
            reason = "；".join(reasons)
            source["reason"] = reason
            issues.append(f"{name}：{reason}")
        else:
            source["status"] = "ok"
            source["reason"] = None
            healthy_count += 1
        sources.append(source)

    enabled_names = {str(row["name"]) for row in rows if int(row["status"]) == 1}
    unexpected_enabled = sorted(enabled_names.difference(EXPECTED_ENABLED_TASK_NAMES))
    return {
        "status": "ok" if not issues else "failed",
        "checked_at": checked_at.isoformat(),
        "expected_source_count": len(EXPECTED_ENABLED_TASK_NAMES),
        "healthy_source_count": healthy_count,
        "enabled_task_count": len(enabled_names),
        "unexpected_enabled_tasks": unexpected_enabled,
        "sources": sources,
        "issues": issues,
        "warnings": warnings,
    }


def _collect_project_signal_counts(
    rows: list[sqlite3.Row],
) -> dict[int, dict[str, int]]:
    counts_by_task: dict[int, dict[str, int]] = {}
    for row in rows:
        task_id = int(row["task_id"])
        counts = counts_by_task.setdefault(
            task_id,
            {label: 0 for label in REQUIRED_PROJECT_SIGNAL_LABELS},
        )
        signal = project_notice_kind(
            [row["title"], row["content_text"]],
            category=row["category"],
            metadata=_parse_metadata_json(row["metadata_json"]),
        )
        if signal in counts:
            counts[signal] += 1
    return counts_by_task


def _parse_metadata_json(value: object) -> dict[str, object]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def backup_database(database: Path, backup_dir: Path, *, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now(timezone.utc)).astimezone().strftime("%Y%m%d-%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / f"data.{timestamp}.db"
    with (
        sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True) as source,
        sqlite3.connect(destination) as target,
    ):
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError(f"数据库备份完整性检查失败：{integrity}")
    return destination


def check_http_endpoint(url: str, *, timeout: float = 8.0) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as response:
            status_code = int(response.status)
        return {"url": url, "status": "ok" if status_code == 200 else "failed", "status_code": status_code}
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {"url": url, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}


def _parse_database_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _print_report(report: dict[str, Any]) -> None:
    database = report["database"]
    print("\n内部交付检查")
    print(f"自动来源：{database['healthy_source_count']}/{database['expected_source_count']} 正常")
    for source in database["sources"]:
        marker = "OK" if source["status"] == "ok" else "FAIL"
        suffix = "" if source["reason"] is None else f" - {source['reason']}"
        print(f"[{marker}] {source['name']}{suffix}")
    for warning in database.get("warnings", []):
        print(f"[WARN] {warning}")
    for endpoint in report["http"]:
        marker = "OK" if endpoint["status"] == "ok" else "FAIL"
        detail = endpoint.get("status_code") or endpoint.get("error")
        print(f"[{marker}] {endpoint['url']} - {detail}")
    backup = report["backup"]
    print(f"[{'OK' if backup['status'] == 'ok' else 'FAIL'}] 数据库备份 - {backup.get('path') or backup.get('error')}")
    print(f"结论：{'可以交付' if report['status'] == 'ok' else '暂不能交付，请先处理 FAIL 项'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="核对内部交付状态并创建 SQLite 一致性备份。")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--skip-http", action="store_true", help="仅用于离线测试，不检查本地前后端。")
    args = parser.parse_args()

    report: dict[str, Any] = {"status": "failed", "database": {}, "http": [], "backup": {}}
    try:
        report["database"] = audit_database(args.database)
    except Exception as exc:  # noqa: BLE001 - CLI must preserve a complete delivery report
        report["database"] = {"status": "failed", "issues": [f"数据库检查失败：{type(exc).__name__}: {exc}"], "sources": [], "healthy_source_count": 0, "expected_source_count": len(EXPECTED_ENABLED_TASK_NAMES)}

    if not args.skip_http:
        report["http"] = [
            check_http_endpoint("http://127.0.0.1:8000/health"),
            check_http_endpoint("http://127.0.0.1:8093/"),
        ]

    try:
        backup = backup_database(args.database, args.backup_dir)
        report["backup"] = {"status": "ok", "path": str(backup.resolve())}
    except Exception as exc:  # noqa: BLE001 - report backup failures without hiding prior checks
        report["backup"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    report["status"] = (
        "ok"
        if report["database"].get("status") == "ok"
        and all(item.get("status") == "ok" for item in report["http"])
        and report["backup"].get("status") == "ok"
        else "failed"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_report(report)
    print(f"详细报告：{args.report.resolve()}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
