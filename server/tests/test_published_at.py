from datetime import datetime, timezone

import pytest

from app.utils.published_at import parse_published_at


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("发布时间：2026-07-24 10:50:34", datetime(2026, 7, 24, 2, 50, 34, tzinfo=timezone.utc)),
        ("发布日期：2026-07-27", datetime(2026, 7, 26, 16, 0, 0, tzinfo=timezone.utc)),
        (
            "发布时间：2026年07月21日 来源：科技部",
            datetime(2026, 7, 20, 16, 0, 0, tzinfo=timezone.utc),
        ),
        ("2026/7/3 09:05", datetime(2026, 7, 3, 1, 5, 0, tzinfo=timezone.utc)),
    ],
)
def test_parse_published_at_normalizes_china_time_to_utc(
    raw: str,
    expected: datetime,
) -> None:
    assert parse_published_at(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "来源：科技部门户网站", "2026-99-99"])
def test_parse_published_at_returns_none_for_missing_or_invalid_values(raw: str | None) -> None:
    assert parse_published_at(raw) is None
