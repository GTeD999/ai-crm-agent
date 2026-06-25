from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from app.core.exceptions import RepositoryError
from app.db.client import get_supabase
from app.db.models import Viewing, ViewingCreate
from app.db.table_names import AI_VIEWINGS_TABLE


class ViewingsRepository:
    async def create(self, data: ViewingCreate) -> Viewing:
        client = await get_supabase()
        response = (
            await client.table(AI_VIEWINGS_TABLE)
            .insert(
                {
                    "user_id": str(data.user_id),
                    "property_id": str(data.property_id),
                    "scheduled_at": data.scheduled_at.isoformat(),
                    "client_phone": data.client_phone,
                    "notes": data.notes,
                }
            )
            .execute()
        )
        if not response.data:
            raise RepositoryError("Failed to create viewing")
        return Viewing.model_validate(response.data[0])


class InMemoryViewingsRepository:
    def __init__(self) -> None:
        self._viewings: dict[UUID, list[Viewing]] = defaultdict(list)

    async def create(self, data: ViewingCreate) -> Viewing:
        from uuid import uuid4

        now = datetime.now(timezone.utc)
        viewing = Viewing(
            id=uuid4(),
            user_id=data.user_id,
            property_id=data.property_id,
            scheduled_at=data.scheduled_at,
            client_phone=data.client_phone,
            notes=data.notes,
            created_at=now,
            updated_at=now,
        )
        self._viewings[data.user_id].append(viewing)
        return viewing
