from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.engine.clinical_trials import (  # noqa: E402
    is_clinical_trial_text_relevant,
)

REPAIR_NOTE = "需求3数据修复：临床试验与配置主题不匹配，已归档。"


def _metadata(raw_metadata: str | None) -> dict[str, object]:
    try:
        value = json.loads(raw_metadata or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _strings(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _topics(metadata: dict[str, object]) -> list[str]:
    values = _strings(metadata.get("topics"))
    if values:
        return values
    return [
        item.strip()
        for item in str(metadata.get("topic") or "").replace("；", "、").split("、")
        if item.strip()
    ]


def _remark(existing: str | None) -> str:
    current = (existing or "").strip()
    if not current:
        return REPAIR_NOTE
    if REPAIR_NOTE in current:
        return current
    return f"{current}\n{REPAIR_NOTE}"


def repair_connection(connection: sqlite3.Connection) -> dict[str, int]:
    report = {
        "clinical_trial_rows": 0,
        "irrelevant_rows": 0,
        "archived": 0,
        "already_archived": 0,
        "missing_topic_contract": 0,
    }
    rows = connection.execute(
        """
        SELECT id, title, metadata_json, is_archived, remark
        FROM collected_data
        WHERE source_url LIKE '%clinicaltrials.gov/study/%'
        ORDER BY id
        """
    ).fetchall()
    report["clinical_trial_rows"] = len(rows)

    for data_id, title, raw_metadata, is_archived, remark in rows:
        metadata = _metadata(raw_metadata)
        topics = _topics(metadata)
        if not topics:
            report["missing_topic_contract"] += 1
            continue
        evidence = [
            title,
            metadata.get("brief_summary"),
            *_strings(metadata.get("conditions")),
            *_strings(metadata.get("keywords")),
            *_strings(metadata.get("interventions")),
            *_strings(metadata.get("drugs")),
        ]
        if any(
            is_clinical_trial_text_relevant(topic, evidence)
            for topic in topics
        ):
            continue

        report["irrelevant_rows"] += 1
        if bool(is_archived):
            report["already_archived"] += 1
            continue
        connection.execute(
            """
            UPDATE collected_data
            SET is_archived = 1, remark = ?
            WHERE id = ?
            """,
            (_remark(remark), data_id),
        )
        report["archived"] += 1

    connection.commit()
    return report


def _backup_database(connection: sqlite3.Connection, database_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(
        f"{database_path.stem}.before-competitor-repair.{timestamp}{database_path.suffix}"
    )
    with sqlite3.connect(backup_path) as destination:
        connection.backup(destination)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive ClinicalTrials.gov rows outside fixed requirement-3 topics."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=REPO_ROOT / "server" / "data.db",
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

    print(
        json.dumps(
            {
                "database": str(database_path),
                "backup": str(backup_path) if backup_path else None,
                "report": report,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
