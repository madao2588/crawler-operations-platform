from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class RetryWindow:
    failure_kind: str
    retry_after: timedelta


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def classify_failure(raw_error: str | None) -> str:
    text = (raw_error or "").strip().lower()
    if not text:
        return "unknown"
    if "429" in text or "too many requests" in text:
        return "rate_limit"
    if "403" in text or "forbidden" in text:
        return "forbidden"
    if "captcha" in text or "challenge" in text or "验证" in (raw_error or ""):
        return "anti_bot"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "err_connection_closed" in text or "connection closed" in text:
        return "network"
    if "network_unreachable" in text or "connection refused" in text or "name or service not known" in text:
        return "network"
    if "err_http_response_code_failure" in text:
        return "http_error"
    return "unknown"


def retry_window_for_failure(raw_error: str | None) -> RetryWindow:
    failure_kind = classify_failure(raw_error)
    retry_after = {
        "timeout": timedelta(minutes=30),
        "network": timedelta(minutes=45),
        "http_error": timedelta(hours=1),
        "forbidden": timedelta(hours=2),
        "rate_limit": timedelta(hours=2),
        "anti_bot": timedelta(hours=3),
        "unknown": timedelta(minutes=30),
    }[failure_kind]
    return RetryWindow(failure_kind=failure_kind, retry_after=retry_after)


def next_retry_at_for_task(
    *,
    last_run_status: str | None,
    last_run_at: datetime | None,
    last_error_message: str | None,
) -> tuple[str | None, datetime | None]:
    status = (last_run_status or "").strip().lower()
    run_at = as_utc(last_run_at)
    if status not in {"failed", "partial"} or run_at is None:
        return None, None
    window = retry_window_for_failure(last_error_message)
    return window.failure_kind, run_at + window.retry_after


def is_retry_backoff_active(
    *,
    now: datetime,
    last_run_status: str | None,
    last_run_at: datetime | None,
    last_error_message: str | None,
) -> tuple[bool, str | None, datetime | None]:
    failure_kind, next_retry_at = next_retry_at_for_task(
        last_run_status=last_run_status,
        last_run_at=last_run_at,
        last_error_message=last_error_message,
    )
    if next_retry_at is None:
        return False, failure_kind, None
    return next_retry_at > now, failure_kind, next_retry_at
