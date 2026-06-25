from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from contextlib import suppress

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.admin import router as admin_router
from app.api.bitrix_webhook import router as bitrix_router
from app.api.telegram_webhook import router as telegram_router
from app.bot.dispatcher import create_bot, create_dispatcher
from app.core.logging import configure_logging, get_logger
from app.core.config import settings
from app.services.scheduler.apscheduler import create_scheduler

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("app_started")
    scheduler = create_scheduler()
    polling_task: asyncio.Task | None = None
    bot = None
    if settings.telegram_enabled:
        scheduler.start()
        logger.info("scheduler_started")
        if settings.telegram_polling_enabled:
            bot = create_bot()
            if bot:
                dp = create_dispatcher()
                await bot.delete_webhook(drop_pending_updates=True)
                polling_task = asyncio.create_task(
                    dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
                )
                logger.info("telegram_polling_started")
    yield
    if polling_task:
        polling_task.cancel()
        with suppress(asyncio.CancelledError):
            await polling_task
        logger.info("telegram_polling_stopped")
    if bot:
        await bot.session.close()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")
    logger.info("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="Novactive AI Manager", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(telegram_router)
    app.include_router(bitrix_router)
    return app


app = create_app()
