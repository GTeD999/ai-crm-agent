from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.services.properties.sync import QuickDealSyncService
from app.services.scheduler.followup_jobs import FollowupJobs


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    jobs = FollowupJobs()
    scheduler.add_job(jobs.run_due, "interval", minutes=60, id="followups", replace_existing=True)
    if settings.quickdeal_feed_url:
        sync = QuickDealSyncService()
        scheduler.add_job(
            sync.sync,
            "interval",
            minutes=settings.quickdeal_sync_interval_minutes,
            id="quickdeal_sync",
            replace_existing=True,
        )
    return scheduler
