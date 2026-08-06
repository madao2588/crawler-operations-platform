import json
import sqlite3

from scripts.repair_competitor_data import REPAIR_NOTE, repair_connection


def _insert(
    connection: sqlite3.Connection,
    *,
    data_id: int,
    title: str,
    topic: str,
    conditions: list[str],
    archived: int = 0,
) -> None:
    connection.execute(
        """
        INSERT INTO collected_data
            (id, title, source_url, metadata_json, is_archived, remark)
        VALUES (?, ?, ?, ?, ?, NULL)
        """,
        (
            data_id,
            title,
            f"https://clinicaltrials.gov/study/NCT{data_id:08d}",
            json.dumps(
                {
                    "source": "ClinicalTrials.gov",
                    "topics": [topic],
                    "conditions": conditions,
                },
                ensure_ascii=False,
            ),
            archived,
        ),
    )


def test_competitor_repair_archives_only_irrelevant_clinical_trials() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE collected_data (
            id INTEGER PRIMARY KEY,
            title TEXT,
            source_url TEXT NOT NULL,
            metadata_json TEXT,
            is_archived INTEGER NOT NULL DEFAULT 0,
            remark TEXT
        )
        """
    )
    _insert(
        connection,
        data_id=1,
        title="Drug therapy in glioblastoma",
        topic="脑胶质瘤",
        conditions=["Glioblastoma"],
    )
    _insert(
        connection,
        data_id=2,
        title="Breast cancer treatment study",
        topic="降尿酸药物",
        conditions=["Breast Cancer"],
    )
    _insert(
        connection,
        data_id=3,
        title="Treatment of acute gouty arthritis",
        topic="降尿酸药物",
        conditions=["Gouty Arthritis"],
    )
    _insert(
        connection,
        data_id=4,
        title="Lung cancer treatment study",
        topic="降尿酸药物",
        conditions=["Lung Cancer"],
        archived=1,
    )
    connection.commit()

    first = repair_connection(connection)
    second = repair_connection(connection)

    assert first == {
        "clinical_trial_rows": 4,
        "irrelevant_rows": 2,
        "archived": 1,
        "already_archived": 1,
        "missing_topic_contract": 0,
    }
    assert second["archived"] == 0
    assert second["already_archived"] == 2
    rows = connection.execute(
        "SELECT id, is_archived, remark FROM collected_data ORDER BY id"
    ).fetchall()
    assert rows[0] == (1, 0, None)
    assert rows[1] == (2, 1, REPAIR_NOTE)
    assert rows[2] == (3, 0, None)
    assert rows[3] == (4, 1, None)
