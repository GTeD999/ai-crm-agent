from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from app.bot.dispatcher import create_bot, create_dispatcher
from app.core.config import settings

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool | str]:
    if not settings.telegram_enabled:
        return {"ok": False, "reason": "telegram_disabled"}
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid Telegram secret token")

    bot = create_bot()
    if not bot:
        return {"ok": False, "reason": "telegram_bot_not_configured"}

    dp = create_dispatcher()
    update = await request.json()
    await dp.feed_raw_update(bot, update)
    return {"ok": True}
