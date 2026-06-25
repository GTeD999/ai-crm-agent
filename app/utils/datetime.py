from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def now_agency_tz() -> datetime:
    return datetime.now(ZoneInfo(settings.agency_timezone))

