from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.db.repositories.users import UsersRepository

router = APIRouter(prefix="/api/bitrix", tags=["bitrix"])


@router.post("/webhook")
async def bitrix_webhook(request: Request) -> dict[str, bool | str]:
    payload = await request.json()
    secret = payload.get("secret") or request.query_params.get("secret")
    if settings.bitrix_incoming_webhook_secret and secret != settings.bitrix_incoming_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid Bitrix webhook secret")

    telegram_id = payload.get("telegram_id") or payload.get("TELEGRAM_ID")
    if not telegram_id:
        # Bitrix webhooks are often form-like or nested. Keep this endpoint safe:
        # log/ignore unknown payloads rather than failing and retrying forever.
        return {"ok": True, "action": "ignored_no_telegram_id"}
    event = payload.get("event")
    if event in {"deal_closed", "dialog_closed"} and telegram_id:
        user = await UsersRepository().get_by_telegram_id(int(telegram_id))
        if user:
            await UsersRepository().set_silent(user.id, False)
            return {"ok": True, "action": "silent_disabled"}

    return {"ok": True, "action": "ignored"}
