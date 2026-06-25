from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from app.core.exceptions import RepositoryError
from app.db.client import get_supabase
from app.db.models import Event, EventCreate
from app.db.table_names import AI_EVENTS_TABLE


class EventsRepository:
    async def save(self, data: EventCreate) -> Event:
        client = await get_supabase()
        response = (
            await client.table(AI_EVENTS_TABLE)
            .insert(
                {
                    "user_id": str(data.user_id) if data.user_id else None,
                    "event_type": data.event_type,
                    "event_data": data.event_data or {},
                }
            )
            .execute()
        )
        if not response.data:
            raise RepositoryError("Failed to save event")
        return Event.model_validate(response.data[0])


class InMemoryEventsRepository:
    def __init__(self) -> None:
        self._events: dict[UUID | None, list[Event]] = defaultdict(list)

    async def save(self, data: EventCreate) -> Event:
        from uuid import uuid4

        event = Event(
            id=uuid4(),
            user_id=data.user_id,
            event_type=data.event_type,
            event_data=data.event_data or {},
            created_at=datetime.now(timezone.utc),
        )
        self._events[data.user_id].append(event)
        return event

    async def list_for_user(self, user_id: UUID) -> list[Event]:
        return self._events[user_id]
