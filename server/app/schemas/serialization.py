"""Consistent JSON datetime wire format (UTC with ``Z``) for API clients."""

from __future__ import annotations

from datetime import datetime, timezone


def dt_to_utc_iso_z(value: datetime | None) -> str | None:
    """Serialize ``datetime`` as RFC3339 UTC ending with ``Z`` (never naive without marker)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    text = value.isoformat(timespec="microseconds")
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text
