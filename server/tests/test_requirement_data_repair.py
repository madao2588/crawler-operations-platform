import json
import sqlite3

from scripts.repair_requirement_data import repair_connection


def test_repair_connection_fixes_only_project_source_rows() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            start_url TEXT NOT NULL,
            parser_rules TEXT
        );
        CREATE TABLE collected_data (
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL,
            title TEXT,
            content_text TEXT,
            source_url TEXT NOT NULL,
            quality_score INTEGER NOT NULL DEFAULT 0,
            category TEXT NOT NULL DEFAULT '未分类',
            metadata_json TEXT,
            review_status TEXT NOT NULL DEFAULT '待关注',
            is_archived BOOLEAN NOT NULL DEFAULT 0,
            remark TEXT,
            published_at DATETIME
        );
        """
    )
    connection.executemany(
        "INSERT INTO tasks (id, name, start_url, parser_rules) VALUES (?, ?, ?, ?)",
        [
            (
                1,
                "湖南省科技厅项目申报采集",
                "https://kjt.hunan.gov.cn/kjt/xxgk/tzgg/index.html",
                "{}",
            ),
            (
                2,
                "行业会议",
                "https://meeting.example/list",
                '{"category":"行业会议"}',
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO collected_data (
            id, task_id, title, content_text, source_url, quality_score,
            category, metadata_json, is_archived, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                10,
                1,
                "李志坚",
                "关于开展2026年度科技项目申报工作的通知\n发布日期：2026年7月24日\n正文",
                "https://kjt.hunan.gov.cn/detail/10.html",
                100,
                "行业会议",
                '{"source":"湖南省科技厅"}',
                0,
                None,
            ),
            (
                11,
                1,
                "国家科技管理信息系统公共服务平台",
                "",
                "https://service.most.gov.cn/xmtj/",
                20,
                "未分类",
                None,
                0,
                None,
            ),
            (
                12,
                2,
                "项目申报交流会议",
                "会议时间：2026年8月1日",
                "https://meeting.example/detail/12",
                90,
                "行业会议",
                '{"kind":"industry_meeting"}',
                0,
                None,
            ),
            (
                13,
                1,
                "关于2026年秋季公办中小学拟录取名单的公示",
                "公办中小学拟录取名单",
                "https://www.hengqin.gov.cn/detail/13.html",
                80,
                "项目申报",
                '{"kind": "project_notice", "source_lane": "requirement_1"}',
                0,
                None,
            ),
            (
                14,
                1,
                "澳门青年创业企业办公场地租金和物业管理费补贴拟发放名单公示",
                "企业补贴拟发放名单",
                "https://www.hengqin.gov.cn/detail/14.html",
                80,
                "项目申报",
                '{"kind": "project_notice", "source_lane": "requirement_1"}',
                0,
                None,
            ),
        ],
    )

    report = repair_connection(connection)

    repaired = connection.execute(
        """
        SELECT title, category, metadata_json, published_at, is_archived
        FROM collected_data WHERE id = 10
        """
    ).fetchone()
    assert repaired is not None
    assert repaired[0] == "关于开展2026年度科技项目申报工作的通知"
    assert repaired[1] == "项目申报"
    assert json.loads(repaired[2])["kind"] == "project_notice"
    assert str(repaired[3]).startswith("2026-07-23T16:00:00")
    assert repaired[4] == 0

    entry_page = connection.execute(
        "SELECT is_archived, remark FROM collected_data WHERE id = 11"
    ).fetchone()
    assert entry_page is not None
    assert entry_page[0] == 1
    assert "入口页" in entry_page[1]

    irrelevant_row = connection.execute(
        "SELECT is_archived, remark FROM collected_data WHERE id = 13"
    ).fetchone()
    assert irrelevant_row is not None
    assert irrelevant_row[0] == 1
    assert "非项目申报或结果公示" in irrelevant_row[1]

    relevant_subsidy = connection.execute(
        "SELECT is_archived, remark FROM collected_data WHERE id = 14"
    ).fetchone()
    assert relevant_subsidy == (0, None)

    untouched = connection.execute(
        "SELECT category, metadata_json, is_archived FROM collected_data WHERE id = 12"
    ).fetchone()
    assert untouched == ("行业会议", '{"kind":"industry_meeting"}', 0)

    assert report["project_rows"] == 4
    assert report["reclassified"] == 2
    assert report["titles_repaired"] == 1
    assert report["dates_backfilled"] == 1
    assert report["entry_pages_archived"] == 1
    assert report["irrelevant_rows_archived"] == 1
