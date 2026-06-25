from __future__ import annotations

from aiogram import Bot, Dispatcher

from app.bot.handlers.message import router as message_router
from app.bot.handlers.start import router as start_router
from app.core.config import settings


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(message_router)
    return dp


def create_bot() -> Bot | None:
    if not settings.telegram_enabled or not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)

