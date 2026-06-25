from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from app.core.exceptions import RepositoryError
from app.db.client import get_supabase
from app.db.models import Followup, FollowupCreate
from app.db.table_names import AI_FOLLOWUPS_TABLE


class FollowupsRepository:
    async def create(self, data: FollowupCreate) -> Followup:
        client = await get_supabase()
        response = (
            await client.table(AI_FOLLOWUPS_TABLE)
            .insert(
                {
                    "user_id": str(data.user_id),
                    "lead_id": str(data.lead_id) if data.lead_id else None,
                    "step": data.step,
                    "scheduled_at": data.scheduled_at.isoformat(),
                    "message": data.message,
                }
            )
            .execute()
        )
        if not response.data:
            raise RepositoryError("Failed to create followup")
        return Followup.model_validate(response.data[0])

    async def due(self, limit: int = 50) -> list[Followup]:
        client = await get_supabase()
        response = (
            await client.table(AI_FOLLOWUPS_TABLE)
            .select("*")
            .eq("status", "pending")
            .lte("scheduled_at", datetime.now(timezone.utc).isoformat())
            .order("scheduled_at")
            .limit(limit)
            .execute()
        )
        return [Followup.model_validate(row) for row in response.data or []]

    async def mark_sent(self, followup_id: UUID) -> None:
        client = await get_supabase()
        await (
            client.table(AI_FOLLOWUPS_TABLE)
            .update({"status": "sent", "sent_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(followup_id))
            .execute()
        )

    async def mark_failed(self, followup_id: UUID) -> None:
        client = await get_supabase()
        await client.table(AI_FOLLOWUPS_TABLE).update({"status": "failed"}).eq("id", str(followup_id)).execute()


class InMemoryFollowupsRepository:
    def __init__(self) -> None:
        self._followups: dict[UUID, list[Followup]] = defaultdict(list)

    async def create(self, data: FollowupCreate) -> Followup:
        from uuid import uuid4

        followup = Followup(
            id=uuid4(),
            user_id=data.user_id,
            lead_id=data.lead_id,
            step=data.step,
            scheduled_at=data.scheduled_at,
            message=data.message,
            created_at=datetime.now(timezone.utc),
        )
        self._followups[data.user_id].append(followup)
        return followup

    async def due(self, limit: int = 50) -> list[Followup]:
        now = datetime.now(timezone.utc)
        items = [
            item
            for followups in self._followups.values()
            for item in followups
            if item.status == "pending" and item.scheduled_at <= now
        ]
        return sorted(items, key=lambda item: item.scheduled_at)[:limit]

    async def mark_sent(self, followup_id: UUID) -> None:
        for user_id, followups in self._followups.items():
            self._followups[user_id] = [
                item.model_copy(update={"status": "sent", "sent_at": datetime.now(timezone.utc)})
                if item.id == followup_id
                else item
                for item in followups
            ]

    async def mark_failed(self, followup_id: UUID) -> None:
        for user_id, followups in self._followups.items():
            self._followups[user_id] = [
                item.model_copy(update={"status": "failed"}) if item.id == followup_id else item
                for item in followups
            ]
