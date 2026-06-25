from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "ok": True,
        "service": "novactive-ai-manager",
        "env": settings.app_env,
        "telegram_enabled": settings.telegram_enabled,
    }
