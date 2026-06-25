from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.db.models import EventCreate, FollowupCreate, LeadUpdate, User, ViewingCreate
from app.db.repositories.events import EventsRepository, InMemoryEventsRepository
from app.db.repositories.followups import FollowupsRepository, InMemoryFollowupsRepository
from app.db.repositories.leads import InMemoryLeadsRepository, LeadsRepository
from app.db.repositories.users import InMemoryUsersRepository, UsersRepository
from app.db.repositories.viewings import InMemoryViewingsRepository, ViewingsRepository
from app.services.properties.models import PropertySearchArgs
from app.services.properties.search import PropertySearchService
from app.services.transfer.manager import TransferManager
from app.utils.phone import normalize_phone


class ToolsDispatcher:
    def __init__(
        self,
        property_search: PropertySearchService | None = None,
        users: UsersRepository | InMemoryUsersRepository | None = None,
        leads: LeadsRepository | InMemoryLeadsRepository | None = None,
        events: EventsRepository | InMemoryEventsRepository | None = None,
        viewings: ViewingsRepository | InMemoryViewingsRepository | None = None,
        followups: FollowupsRepository | InMemoryFollowupsRepository | None = None,
        transfer_manager: TransferManager | None = None,
    ) -> None:
        self.property_search = property_search or PropertySearchService()
        self.users = users or UsersRepository()
        self.leads = leads or LeadsRepository()
        self.events = events or EventsRepository()
        self.viewings = viewings or ViewingsRepository()
        self.followups = followups or FollowupsRepository()
        self.transfer_manager = transfer_manager or TransferManager(self.users, self.leads, self.events)
        self.registry: dict[str, ToolHandler] = {
            "search_properties": self.search_properties,
            "get_property_details": self.get_property_details,
            "search_knowledge_base": self.search_knowledge_base,
            "save_lead": self.save_lead,
            "book_viewing": self.book_viewing,
            "request_pd_consent": self.request_pd_consent,
            "confirm_pd_consent": self.confirm_pd_consent,
            "transfer_to_manager": self.transfer_to_manager,
        }

    async def dispatch(self, name: str, args: dict[str, Any], user: User) -> dict[str, Any]:
        handler = self.registry.get(name)
        if not handler:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        return await handler(user=user, **args)

    async def search_properties(self, user: User, **kwargs: Any) -> dict[str, Any]:
        args = PropertySearchArgs.model_validate(kwargs)
        try:
            properties = await self.property_search.search_properties(args)
        except Exception as exc:
            return {"ok": False, "error": "property_search_failed", "message": str(exc)}
        return {"ok": True, "properties": [item.model_dump(mode="json") for item in properties]}

    async def get_property_details(self, user: User, property_id: str, **kwargs: Any) -> dict[str, Any]:
        property_card = await self.property_search.get_property_details(property_id)
        if not property_card:
            return {"ok": False, "error": "property_not_found"}
        return {"ok": True, "property": property_card.model_dump(mode="json")}

    async def search_knowledge_base(self, user: User, query: str, category: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "items": [],
            "message": "База знаний пока не загружена. Сложный вопрос лучше передать менеджеру.",
        }

    async def save_lead(self, user: User, **kwargs: Any) -> dict[str, Any]:
        if ("phone" in kwargs or "name" in kwargs) and not user.pd_consent:
            return {"ok": False, "error": "pd_consent_required"}
        lead = await self.leads.upsert_for_user(user.id, LeadUpdate.model_validate(kwargs))
        await self.events.save(EventCreate(user_id=user.id, event_type="lead_saved", event_data=lead.model_dump(mode="json")))
        return {"ok": True, "lead": lead.model_dump(mode="json")}

    async def book_viewing(
        self,
        user: User,
        property_id: str,
        scheduled_at: str,
        client_phone: str,
        notes: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not user.pd_consent:
            return {"ok": False, "error": "pd_consent_required"}
        phone = normalize_phone(client_phone)
        viewing = await self.viewings.create(
            ViewingCreate(
                user_id=user.id,
                property_id=property_id,
                scheduled_at=datetime.fromisoformat(scheduled_at),
                client_phone=phone,
                notes=notes,
            )
        )
        await self.events.save(EventCreate(user_id=user.id, event_type="viewing_booked", event_data=viewing.model_dump(mode="json")))
        return {"ok": True, "viewing": viewing.model_dump(mode="json")}

    async def request_pd_consent(self, user: User, **kwargs: Any) -> dict[str, Any]:
        await self.events.save(EventCreate(user_id=user.id, event_type="pd_consent_requested", event_data={}))
        return {"ok": True, "message": "consent_requested"}

    async def confirm_pd_consent(self, user: User, **kwargs: Any) -> dict[str, Any]:
        await self.users.confirm_pd_consent(user.id)
        user.pd_consent = True
        user.pd_consent_at = datetime.now(timezone.utc)
        await self.events.save(EventCreate(user_id=user.id, event_type="pd_consent_confirmed", event_data={}))
        return {"ok": True}

    async def transfer_to_manager(
        self,
        user: User,
        reason: str,
        summary: str,
        urgency: str = "normal",
        property_id: str | None = None,
        client_contact_status: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if property_id:
            property_card = await self.property_search.get_property_details(property_id)
            if property_card:
                summary = (
                    f"{summary}\n\n"
                    "Связанный объект:\n"
                    f"- {property_card.title}\n"
                    f"- Цена: {property_card.price}\n"
                    f"- Ссылка: {property_card.site_url or 'нет'}\n"
                    f"- Агент объекта: {property_card.manager_name or 'не указан'} "
                    f"{property_card.manager_phone or ''} {property_card.manager_email or ''}\n"
                )
        lead_id = await self.transfer_manager.transfer(user.id, reason=reason, summary=summary, telegram=str(user.telegram_id))
        return {
            "ok": True,
            "bitrix_lead_id": lead_id,
            "silent": True,
            "urgency": urgency,
            "client_contact_status": client_contact_status,
        }

    async def schedule_followup(self, user: User, step: int = 1, message: str | None = None, **kwargs: Any) -> dict[str, Any]:
        lead = await self.leads.get_active_by_user_id(user.id)
        scheduled_at = datetime.now(timezone.utc) + timedelta(hours=settings.followup_step_1_hours)
        if step == 2:
            scheduled_at = datetime.now(timezone.utc) + timedelta(days=settings.followup_step_2_days)
        elif step == 3:
            scheduled_at = datetime.now(timezone.utc) + timedelta(days=settings.followup_step_3_days)
        followup = await self.followups.create(
            FollowupCreate(user_id=user.id, lead_id=lead.id if lead else None, step=step, scheduled_at=scheduled_at, message=message)
        )
        return {"ok": True, "followup": followup.model_dump(mode="json")}


ToolHandler = Callable[..., Awaitable[dict[str, Any]]]
