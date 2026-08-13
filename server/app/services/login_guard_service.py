from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings


@dataclass(slots=True)
class LoginAttemptState:
    failures: int = 0
    first_failure_at: datetime | None = None
    blocked_until: datetime | None = None


class LoginGuardService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._states: dict[str, LoginAttemptState] = {}

    def ensure_allowed(self, username: str) -> None:
        key = self._normalize_key(username)
        state = self._states.get(key)
        if state is None:
            return
        now = datetime.now(UTC)
        if state.blocked_until and state.blocked_until > now:
            remaining_minutes = max(
                1,
                int((state.blocked_until - now).total_seconds() // 60) or 1,
            )
            raise PermissionError(f"登录尝试过多，请 {remaining_minutes} 分钟后再试")
        if state.blocked_until and state.blocked_until <= now:
            self._states.pop(key, None)

    def record_failure(self, username: str) -> None:
        key = self._normalize_key(username)
        now = datetime.now(UTC)
        window = timedelta(minutes=self.settings.login_rate_limit_window_minutes)
        state = self._states.get(key)
        if state is None or state.first_failure_at is None or state.first_failure_at + window <= now:
            state = LoginAttemptState(failures=1, first_failure_at=now)
            self._states[key] = state
            return

        state.failures += 1
        if state.failures >= self.settings.login_rate_limit_attempts:
            state.blocked_until = now + timedelta(minutes=self.settings.login_rate_limit_block_minutes)

    def record_success(self, username: str) -> None:
        self._states.pop(self._normalize_key(username), None)

    @staticmethod
    def _normalize_key(username: str) -> str:
        return username.strip().casefold()
