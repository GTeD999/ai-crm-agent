from __future__ import annotations

from uuid import UUID

from app.core.exceptions import ExternalApiError
from app.db.models import EventCreate, LeadStatus, LeadUpdate, MessageRole
from app.db.repositories.events import EventsRepository, InMemoryEventsRepository
from app.db.repositories.leads import InMemoryLeadsRepository, LeadsRepository
from app.db.repositories.messages import InMemoryMessagesRepository, MessagesRepository
from app.db.repositories.users import InMemoryUsersRepository, UsersRepository
from app.services.crm.bitrix_client import BitrixClient


class TransferManager:
    def __init__(
        self,
        users: UsersRepository | InMemoryUsersRepository,
        leads: LeadsRepository | InMemoryLeadsRepository,
        events: EventsRepository | InMemoryEventsRepository,
        messages: MessagesRepository | InMemoryMessagesRepository | None = None,
        bitrix: BitrixClient | None = None,
    ) -> None:
        self.users = users
        self.leads = leads
        self.events = events
        self.messages = messages or MessagesRepository()
        self.bitrix = bitrix or BitrixClient()

    async def transfer(self, user_id: UUID, reason: str, summary: str, telegram: str | None = None) -> int | None:
        bitrix_lead_id: int | None = None
        bitrix_task_id: int | None = None
        user = await self.users.get_by_id(user_id)
        lead = await self.leads.get_active_by_user_id(user_id)
        if not lead:
            lead = await self.leads.upsert_for_user(
                user_id,
                LeadUpdate(status=LeadStatus.HOT, transfer_reason=reason, additional_notes=summary),
            )
        full_context = await self.build_transfer_context(
            user_id=user_id,
            reason=reason,
            ai_summary=summary,
            telegram=telegram,
        )

        try:
            if self.bitrix.configured:
                bitrix_lead_id = await self.bitrix.create_lead(
                    title=f"AI-лид Telegram: {reason}",
                    summary=full_context,
                    telegram=telegram,
                    name=user.first_name if user else None,
                    phone=user.phone if user else None,
                )
                if bitrix_lead_id:
                    await self.bitrix.add_timeline_comment(bitrix_lead_id, full_context, entity_type="lead")
                    bitrix_task_id = await self.bitrix.create_lead_activity(
                        bitrix_lead_id,
                        subject=f"AI-лид: связаться и уточнить ({reason})",
                        description=full_context,
                        phone=user.phone if user else None,
                    )
        except ExternalApiError as error:
            await self.events.save(
                EventCreate(
                    user_id=user_id,
                    event_type="bitrix_transfer_failed",
                    event_data={"reason": reason, "error": str(error)},
                )
            )

        if lead:
            await self.leads.upsert_for_user(
                user_id,
                LeadUpdate(
                    bitrix_lead_id=bitrix_lead_id,
                    bitrix_deal_id=None,
                    status=LeadStatus.TRANSFERRED,
                    transfer_reason=reason,
                    additional_notes=summary,
                ),
            )
            await self.leads.mark_transferred(lead.id, reason, None)
        await self.users.set_silent(user_id, True)
        await self.events.save(
            EventCreate(
                user_id=user_id,
                event_type="transferred_to_manager",
                event_data={"reason": reason, "bitrix_lead_id": bitrix_lead_id, "bitrix_task_id": bitrix_task_id},
            )
        )
        return bitrix_lead_id

    async def build_transfer_context(
        self,
        user_id: UUID,
        reason: str,
        ai_summary: str,
        telegram: str | None = None,
    ) -> str:
        user = await self.users.get_by_id(user_id)
        lead = await self.leads.get_active_by_user_id(user_id)
        messages = await self.messages.last_n(user_id, n=60)
        dialog_lines = []
        for message in messages:
            if message.role == MessageRole.TOOL:
                continue
            role = "Клиент" if message.role == MessageRole.USER else "AI"
            content = message.content.strip()
            if content:
                dialog_lines.append(f"{role}: {content}")

        user_name = " ".join(part for part in [user.first_name if user else None, user.last_name if user else None] if part)
        lead_fields = format_lead_fields(lead)
        return "\n".join(
            [
                "НОВЫЙ AI-ЛИД ИЗ TELEGRAM",
                "",
                "КЛИЕНТ",
                f"Имя: {user_name or 'не указано'}",
                f"Телефон: {user.phone if user and user.phone else 'не указан'}",
                f"Telegram: @{user.telegram_username if user and user.telegram_username else 'не указан'}",
                f"Telegram ID: {telegram or (str(user.telegram_id) if user else 'не указан')}",
                "",
                "СТАТУС",
                f"Причина передачи: {format_reason(reason)}",
                f"Статус лида: {format_status(lead.status if lead else LeadStatus.HOT)}",
                "",
                "КРАТКОЕ РЕЗЮМЕ AI",
                clean_summary(ai_summary),
                "",
                "ПАРАМЕТРЫ ЗАПРОСА",
                lead_fields or "Параметры пока не заполнены. Смотрите историю диалога ниже.",
                "",
                "ИСТОРИЯ ДИАЛОГА",
                "\n".join(dialog_lines[-60:]) or "История сообщений пуста.",
            ]
        )


def clean_summary(summary: str | None) -> str:
    if not summary:
        return "AI не передал summary."
    if summary.startswith("Новый AI-лид") or summary.startswith("НОВЫЙ AI-ЛИД"):
        return "Клиент передан менеджеру. Детали смотрите в истории диалога."
    return summary.strip()


def format_lead_fields(lead) -> str:
    if not lead:
        return ""

    labels = {
        "property_type": "Тип объекта",
        "deal_type": "Тип сделки",
        "new_or_secondary": "Новостройка/вторичка",
        "rooms": "Комнатность",
        "price_min": "Бюджет от",
        "price_max": "Бюджет до",
        "area_min": "Площадь от",
        "area_max": "Площадь до",
        "districts": "Районы",
        "city": "Город",
        "purpose": "Цель покупки",
        "timeline": "Срок",
        "mortgage_needed": "Ипотека",
        "has_first_payment": "Первоначальный взнос",
        "first_payment_amount": "Сумма первого взноса",
        "selling_other_property": "Продает другой объект",
        "materinsky_capital": "Материнский капитал",
        "score": "Скоринг",
    }
    money_fields = {"price_min", "price_max", "first_payment_amount"}
    area_fields = {"area_min", "area_max"}
    lines = []
    data = lead.model_dump(mode="json")
    for key, label in labels.items():
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if key == "score" and value == 0:
            continue
        if isinstance(value, bool):
            value = "да" if value else "нет"
        elif key in money_fields and isinstance(value, int):
            value = f"{value:,}".replace(",", " ") + " руб."
        elif key in area_fields:
            value = f"{value} м2"
        elif isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def format_reason(reason: str) -> str:
    labels = {
        "ready_to_close": "клиент оставил контакт / готов к следующему шагу",
        "human_request": "клиент попросил менеджера",
        "legal_question": "юридический вопрос",
        "complaint": "жалоба или негатив",
        "object_agent_question": "нужно уточнение по объекту",
        "selected_commercial_property": "клиент выбрал коммерческий объект",
        "premium_budget": "премиальный запрос",
    }
    return labels.get(reason, reason)


def format_status(status: LeadStatus | str) -> str:
    value = status.value if hasattr(status, "value") else str(status)
    labels = {
        "new": "новый",
        "qualified": "квалифицирован",
        "hot": "горячий",
        "transferred": "передан менеджеру",
        "cold": "холодный",
        "closed_won": "закрыт успешно",
        "closed_lost": "закрыт неуспешно",
    }
    return labels.get(value, value)
