from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.exceptions import RepositoryError
from app.db.client import get_supabase
from app.db.models import Lead, LeadStatus, LeadUpdate
from app.db.table_names import AI_LEADS_TABLE


class LeadsRepository:
    async def get_active_by_user_id(self, user_id: UUID) -> Lead | None:
        client = await get_supabase()
        response = (
            await client.table(AI_LEADS_TABLE)
            .select("*")
            .eq("user_id", str(user_id))
            .not_.in_(
                "status",
                [LeadStatus.TRANSFERRED.value, LeadStatus.CLOSED_WON.value, LeadStatus.CLOSED_LOST.value],
            )
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return Lead.model_validate(response.data[0])

    async def upsert_for_user(self, user_id: UUID, update: LeadUpdate) -> Lead:
        existing = await self.get_active_by_user_id(user_id)
        payload = clean_payload(update)
        client = await get_supabase()

        if existing:
            response = (
                await client.table(AI_LEADS_TABLE)
                .update(payload)
                .eq("id", str(existing.id))
                .execute()
            )
        else:
            response = await client.table(AI_LEADS_TABLE).insert({"user_id": str(user_id), **payload}).execute()

        if not response.data:
            raise RepositoryError("Failed to upsert lead")
        return Lead.model_validate(response.data[0])

    async def mark_transferred(self, lead_id: UUID, reason: str, bitrix_deal_id: int | None = None) -> None:
        client = await get_supabase()
        await (
            client.table(AI_LEADS_TABLE)
            .update(
                {
                    "status": LeadStatus.TRANSFERRED.value,
                    "transfer_reason": reason,
                    "bitrix_deal_id": bitrix_deal_id,
                    "transferred_to_manager_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", str(lead_id))
            .execute()
        )


class InMemoryLeadsRepository:
    def __init__(self) -> None:
        self._leads: dict[UUID, Lead] = {}

    async def get_active_by_user_id(self, user_id: UUID) -> Lead | None:
        lead = self._leads.get(user_id)
        if lead and lead.status not in {LeadStatus.TRANSFERRED, LeadStatus.CLOSED_WON, LeadStatus.CLOSED_LOST}:
            return lead
        return None

    async def upsert_for_user(self, user_id: UUID, update: LeadUpdate) -> Lead:
        from uuid import uuid4

        now = datetime.now(timezone.utc)
        existing = self._leads.get(user_id)
        payload = clean_payload(update)
        if existing:
            lead = Lead.model_validate({**existing.model_dump(), **payload, "updated_at": now})
        else:
            lead = Lead(
                id=uuid4(),
                user_id=user_id,
                created_at=now,
                updated_at=now,
                **payload,
            )
        self._leads[user_id] = lead
        return lead

    async def mark_transferred(self, lead_id: UUID, reason: str, bitrix_deal_id: int | None = None) -> None:
        for user_id, lead in self._leads.items():
            if lead.id == lead_id:
                self._leads[user_id] = lead.model_copy(
                    update={
                        "status": LeadStatus.TRANSFERRED,
                        "transfer_reason": reason,
                        "bitrix_deal_id": bitrix_deal_id,
                        "transferred_to_manager_at": datetime.now(timezone.utc),
                    }
                )
                return


def clean_payload(update: LeadUpdate) -> dict:
    data = update.model_dump(exclude_unset=True)
    return {key: value.value if hasattr(value, "value") else value for key, value in data.items() if value is not None}
