from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.utils.notice import PROJECT_NOTICE_IRRELEVANCE_KEYWORDS

PROJECT_START_URLS = frozenset(
    {
        "https://service.most.gov.cn/kjjh_tztg/",
        "https://gdstc.gd.gov.cn/zwgk_n/tzgg/",
        "https://gdstc.gd.gov.cn/zwgk_n/tzgg/index.html",
        "https://kjj.gz.gov.cn/xxgk/kjglhxmjf/",
        "https://www.hp.gov.cn/gzjg/qzfgwhgzbm/qkxjsj/tzgg/index.html",
        "https://www.hengqin.gov.cn/macao_zh_hans/zwgk/tzgg/gg/?page=1",
        "https://kjt.hunan.gov.cn/kjt/xxgk/tzgg/index.html",
        "http://kjt.hunan.gov.cn/kjt/xxgk/tzgg/index.html",
        "https://kjj.changsha.gov.cn/zfxxgk/tzgg_27202/",
        "http://kjj.changsha.gov.cn/zfxxgk/tzgg_27202/",
    }
)

LEGACY_ENTRY_URLS = frozenset(
    {
        "https://service.most.gov.cn/xmtj/",
        "http://service.most.gov.cn/xmtj/",
    }
)

GENERIC_OR_BAD_TITLES = frozenset(
    {
        "",
        "李志坚",
        "通知公告 -湖南省科技厅",
        "通知公告-湖南省科技厅",
        "国家科技管理信息系统公共服务平台",
        "国家科技管理信息系统 公共服务平台",
    }
)

PROJECT_TITLE_MARKERS = (
    "申报",
    "项目",
    "通知",
    "公告",
    "公示",
    "立项",
    "征集",
    "评审",
)

DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})年\s*(?P<month>\d{1,2})月\s*(?P<day>\d{1,2})日"),
    re.compile(r"(?P<year>20\d{2})[-/.](?P<month>\d{1,2})[-/.](?P<day>\d{1,2})"),
)


def _project_task_ids(connection: sqlite3.Connection) -> list[int]:
    task_ids: list[int] = []
    rows = connection.execute(
        "SELECT id, name, start_url, parser_rules FROM tasks"
    ).fetchall()
    for task_id, name, start_url, raw_rules in rows:
        rules: dict[str, object] = {}
        if raw_rules:
            try:
                loaded = json.loads(raw_rules)
                if isinstance(loaded, dict):
                    rules = loaded
            except (TypeError, ValueError):
                rules = {}
        if (
            str(start_url or "") in PROJECT_START_URLS
            or rules.get("category") == "项目申报"
            or "项目申报" in str(name or "")
        ):
            task_ids.append(int(task_id))
    return task_ids


def _normalized_project_metadata(raw_metadata: str | None) -> str:
    metadata: dict[str, object] = {}
    if raw_metadata:
        try:
            loaded = json.loads(raw_metadata)
            if isinstance(loaded, dict):
                metadata.update(loaded)
        except (TypeError, ValueError):
            pass
    metadata["kind"] = "project_notice"
    metadata["source_lane"] = "requirement_1"
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _replacement_title(title: str | None, content_text: str | None) -> str | None:
    normalized_title = " ".join((title or "").split())
    if normalized_title not in GENERIC_OR_BAD_TITLES and len(normalized_title) >= 6:
        return None

    for raw_line in (content_text or "").splitlines():
        candidate = " ".join(raw_line.strip(" \t\r\n：:").split())
        if not 8 <= len(candidate) <= 200:
            continue
        if candidate.startswith(("来源", "作者", "发布时间", "发布日期", "信息来源")):
            continue
        if any(marker in candidate for marker in PROJECT_TITLE_MARKERS):
            return candidate
    return None


def _published_at_from_text(*parts: str | None) -> str | None:
    text = "\n".join(part or "" for part in parts)
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        try:
            local_value = datetime(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
                tzinfo=ZoneInfo("Asia/Shanghai"),
            )
        except ValueError:
            continue
        return local_value.astimezone(UTC).isoformat()
    return None


def _append_remark(existing: str | None, note: str) -> str:
    current = (existing or "").strip()
    if not current:
        return note
    if note in current:
        return current
    return f"{current}\n{note}"


def _archive_remark(existing: str | None) -> str:
    return _append_remark(
        existing,
        "需求数据修复：入口页不是有效公告详情，已归档。",
    )


def _irrelevant_archive_remark(existing: str | None) -> str:
    return _append_remark(
        existing,
        "需求数据修复：标题属于非项目申报或结果公示内容，已归档。",
    )


def _is_irrelevant_project_title(title: str | None) -> bool:
    normalized = " ".join((title or "").split()).lower()
    return bool(normalized) and any(
        keyword.lower() in normalized
        for keyword in PROJECT_NOTICE_IRRELEVANCE_KEYWORDS
    )


def repair_connection(connection: sqlite3.Connection) -> dict[str, int]:
    report = {
        "project_rows": 0,
        "reclassified": 0,
        "metadata_repaired": 0,
        "titles_repaired": 0,
        "dates_backfilled": 0,
        "entry_pages_archived": 0,
        "irrelevant_rows_archived": 0,
    }
    task_ids = _project_task_ids(connection)
    if not task_ids:
        return report

    placeholders = ",".join("?" for _ in task_ids)
    rows = connection.execute(
        f"""
        SELECT id, title, content_text, source_url, category, metadata_json,
               published_at, is_archived, remark
        FROM collected_data
        WHERE task_id IN ({placeholders})
        ORDER BY id
        """,
        task_ids,
    ).fetchall()
    report["project_rows"] = len(rows)

    for (
        data_id,
        title,
        content_text,
        source_url,
        category,
        metadata_json,
        published_at,
        is_archived,
        remark,
    ) in rows:
        updates: dict[str, object] = {}
        if category != "项目申报":
            updates["category"] = "项目申报"
            report["reclassified"] += 1

        normalized_metadata = _normalized_project_metadata(metadata_json)
        if normalized_metadata != (metadata_json or ""):
            updates["metadata_json"] = normalized_metadata
            report["metadata_repaired"] += 1

        better_title = _replacement_title(title, content_text)
        if better_title and better_title != title:
            updates["title"] = better_title
            report["titles_repaired"] += 1

        if published_at is None:
            inferred_date = _published_at_from_text(
                better_title or title,
                content_text,
            )
            if inferred_date:
                updates["published_at"] = inferred_date
                report["dates_backfilled"] += 1

        if (
            not bool(is_archived)
            and str(source_url or "") in (PROJECT_START_URLS | LEGACY_ENTRY_URLS)
        ):
            updates["is_archived"] = 1
            updates["remark"] = _archive_remark(remark)
            report["entry_pages_archived"] += 1
        elif not bool(is_archived) and _is_irrelevant_project_title(better_title or title):
            updates["is_archived"] = 1
            updates["remark"] = _irrelevant_archive_remark(remark)
            report["irrelevant_rows_archived"] += 1

        if not updates:
            continue
        columns = ", ".join(f"{column} = ?" for column in updates)
        connection.execute(
            f"UPDATE collected_data SET {columns} WHERE id = ?",
            [*updates.values(), data_id],
        )

    connection.commit()
    return report


def _backup_database(connection: sqlite3.Connection, database_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(
        f"{database_path.stem}.before-requirement-repair.{timestamp}{database_path.suffix}"
    )
    with sqlite3.connect(backup_path) as destination:
        connection.backup(destination)
    return backup_path


def main() -> int:
    crawler_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Idempotently repair requirement 1 project-notice data."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=crawler_root / "server" / "data.db",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip the default SQLite online backup.",
    )
    args = parser.parse_args()
    database_path = args.database.resolve()
    if not database_path.exists():
        raise FileNotFoundError(f"Database does not exist: {database_path}")

    with sqlite3.connect(database_path, timeout=30) as connection:
        backup_path = (
            None
            if args.no_backup
            else _backup_database(connection, database_path)
        )
        report = repair_connection(connection)

    output = {
        "database": str(database_path),
        "backup": str(backup_path) if backup_path else None,
        "report": report,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
