from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalApiError


class BitrixClient:
    def __init__(self, webhook_base_url: str | None = None) -> None:
        self.webhook_base_url = (webhook_base_url or settings.bitrix_webhook_url or "").rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.webhook_base_url)

    async def call(self, method: str, payload: dict) -> dict:
        if not self.configured:
            raise ExternalApiError("Bitrix webhook is not configured")

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"{self.webhook_base_url}/{method}.json", json=payload)
        if response.status_code >= 400:
            raise ExternalApiError(f"Bitrix {method} failed with HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        if "error" in data:
            raise ExternalApiError(f"Bitrix {method} failed: {data.get('error_description') or data['error']}")
        return data

    async def create_lead(
        self,
        title: str,
        summary: str,
        telegram: str | None = None,
        name: str | None = None,
        phone: str | None = None,
    ) -> int | None:
        fields = {
            "TITLE": title,
            "NAME": name or "Telegram клиент",
            "COMMENTS": trim_for_bitrix(summary),
            "SOURCE_ID": "OTHER",
            "SOURCE_DESCRIPTION": f"AI Telegram bot{f' Telegram: {telegram}' if telegram else ''}",
        }
        if settings.bitrix_default_manager_id:
            fields["ASSIGNED_BY_ID"] = settings.bitrix_default_manager_id
        if phone:
            fields["PHONE"] = [{"VALUE": phone, "VALUE_TYPE": "WORK"}]

        data = await self.call("crm.lead.add", {"fields": fields})
        result = data.get("result")
        return int(result) if result else None

    async def create_deal(
        self,
        title: str,
        summary: str,
        telegram: str | None = None,
        lead_id: int | None = None,
    ) -> int | None:
        fields = {
            "TITLE": title,
            "COMMENTS": trim_for_bitrix(summary),
        }
        if settings.bitrix_default_manager_id:
            fields["ASSIGNED_BY_ID"] = settings.bitrix_default_manager_id
        if settings.bitrix_deal_category_id:
            fields["CATEGORY_ID"] = settings.bitrix_deal_category_id
        if telegram:
            fields["UF_CRM_TELEGRAM"] = telegram

        data = await self.call("crm.deal.add", {"fields": fields})
        result = data.get("result")
        return int(result) if result else None

    async def add_timeline_comment(self, entity_id: int, comment: str, entity_type: str = "deal") -> None:
        await self.call(
            "crm.timeline.comment.add",
            {
                "fields": {
                    "ENTITY_ID": entity_id,
                    "ENTITY_TYPE": entity_type,
                    "COMMENT": trim_for_bitrix(comment),
                }
            },
        )

    async def create_task(
        self,
        title: str,
        description: str,
        responsible_id: int | None = None,
    ) -> int | None:
        fields = {
            "TITLE": title,
            "DESCRIPTION": trim_for_bitrix(description, limit=6000),
            "RESPONSIBLE_ID": responsible_id or settings.bitrix_default_manager_id or 1,
        }
        data = await self.call("tasks.task.add", {"fields": fields})
        result = data.get("result") or {}
        task = result.get("task") if isinstance(result, dict) else None
        task_id = task.get("id") if isinstance(task, dict) else result.get("id") if isinstance(result, dict) else None
        return int(task_id) if task_id else None

    async def create_lead_activity(
        self,
        lead_id: int,
        subject: str,
        description: str,
        phone: str | None = None,
        responsible_id: int | None = None,
    ) -> int | None:
        now = datetime.now(timezone.utc)
        fields = {
            "OWNER_TYPE_ID": 1,
            "OWNER_ID": lead_id,
            "TYPE_ID": 2,
            "SUBJECT": subject,
            "DESCRIPTION": trim_for_bitrix(description, limit=6000),
            "RESPONSIBLE_ID": responsible_id or settings.bitrix_default_manager_id or 1,
            "START_TIME": now.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "END_TIME": (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S%z"),
            "PRIORITY": 3,
        }
        if phone:
            fields["COMMUNICATIONS"] = [
                {
                    "TYPE": "PHONE",
                    "VALUE": phone,
                    "ENTITY_ID": lead_id,
                    "ENTITY_TYPE_ID": 1,
                }
            ]
        data = await self.call("crm.activity.add", {"fields": fields})
        result = data.get("result")
        return int(result) if result else None


def trim_for_bitrix(text: str, limit: int = 30000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 80] + "\n\n[Контекст обрезан по лимиту Bitrix. Полная история хранится в ai_manager_messages.]"
