from datetime import UTC, datetime

from app.schemas.serialization import dt_to_utc_iso_z
from app.schemas.keyword_rule import KeywordRuleResponse
from app.schemas.task import TaskRead, TaskStatus


def test_dt_to_utc_iso_z_naive_treated_as_utc() -> None:
    naive = datetime(2026, 4, 21, 2, 57, 13, 589635)
    out = dt_to_utc_iso_z(naive)
    assert out is not None
    assert out.endswith("Z")
    assert "2026-04-21T02:57:13.589635" in out


def test_task_read_model_dump_json_uses_z_suffix() -> None:
    task = TaskRead(
        id=6,
        name="t",
        start_url="https://example.com",
        cron_expr="0 * * * *",
        status=TaskStatus.ENABLED,
        parser_rules=None,
        last_run_at=datetime(2026, 4, 21, 2, 57, 13, 589635, tzinfo=UTC),
        last_success_at=datetime(2026, 4, 21, 2, 57, 13, 817505, tzinfo=UTC),
        last_error_message=None,
        created_at=datetime(2026, 4, 1, 0, 0, 0, tzinfo=UTC),
    )
    data = task.model_dump(mode="json")
    assert str(data["last_run_at"]).endswith("Z")
    assert str(data["last_success_at"]).endswith("Z")
    assert str(data["created_at"]).endswith("Z")


def test_keyword_rule_response_serializes_sqlite_times_as_utc() -> None:
    rule = KeywordRuleResponse(
        id=1,
        word="项目申报",
        is_high_priority=True,
        is_active=True,
        is_default=True,
        created_at=datetime(2026, 8, 4, 5, 46, 0),
        updated_at=datetime(2026, 8, 4, 5, 46, 0),
    )

    data = rule.model_dump(mode="json")

    assert data["created_at"] == "2026-08-04T05:46:00.000000Z"
    assert data["updated_at"] == "2026-08-04T05:46:00.000000Z"
