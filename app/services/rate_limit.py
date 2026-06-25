from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.config import settings


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    reason: str | None = None


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._minute: dict[int, deque[datetime]] = defaultdict(deque)
        self._hour: dict[int, deque[datetime]] = defaultdict(deque)

    def check(self, telegram_id: int) -> RateLimitResult:
        now = datetime.now(timezone.utc)
        minute_window = now - timedelta(minutes=1)
        hour_window = now - timedelta(hours=1)

        minute_items = self._minute[telegram_id]
        hour_items = self._hour[telegram_id]
        while minute_items and minute_items[0] < minute_window:
            minute_items.popleft()
        while hour_items and hour_items[0] < hour_window:
            hour_items.popleft()

        if len(minute_items) >= settings.rate_limit_messages_per_minute:
            return RateLimitResult(False, "minute")
        if len(hour_items) >= settings.rate_limit_messages_per_hour:
            return RateLimitResult(False, "hour")

        minute_items.append(now)
        hour_items.append(now)
        return RateLimitResult(True)

