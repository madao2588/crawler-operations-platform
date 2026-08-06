from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")
PUBLISHED_AT_PATTERN = re.compile(
    r"(?P<year>20\d{2})\s*[-年/.]\s*"
    r"(?P<month>\d{1,2})\s*[-月/.]\s*"
    r"(?P<day>\d{1,2})(?:\s*日)?"
)
PUBLISHED_TIME_PATTERN = re.compile(
    r"\s*[T ]\s*(?P<hour>\d{1,2})"
    r"\s*:\s*(?P<minute>\d{1,2})"
    r"(?:\s*:\s*(?P<second>\d{1,2}))?"
)


def parse_published_at(raw: str | None) -> datetime | None:
    """Parse a source-page China local publication time and normalize it to UTC."""
    if not raw:
        return None
    match = PUBLISHED_AT_PATTERN.search(raw)
    if match is None:
        return None
    time_match = PUBLISHED_TIME_PATTERN.match(raw, match.end())

    try:
        local_time = datetime(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
            int(time_match.group("hour") if time_match else 0),
            int(time_match.group("minute") if time_match else 0),
            int(time_match.group("second") or 0) if time_match else 0,
            tzinfo=CHINA_TIMEZONE,
        )
    except ValueError:
        return None
    return local_time.astimezone(timezone.utc)
