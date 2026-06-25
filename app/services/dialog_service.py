from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.models import EventCreate, MessageCreate, MessageRole, UserCreate
from app.db.repositories.events import EventsRepository, InMemoryEventsRepository
from app.db.repositories.leads import InMemoryLeadsRepository, LeadsRepository
from app.db.repositories.messages import InMemoryMessagesRepository, MessagesRepository
from app.db.repositories.settings import is_ai_enabled
from app.db.repositories.users import InMemoryUsersRepository, UsersRepository
from app.services.ai.dialog_engine import DialogEngine, InMemoryDialogStateRepository
from app.services.ai.classifier import IntentClassifier
from app.services.ai.chat import AIChatService
from app.services.rate_limit import InMemoryRateLimiter
from app.services.transfer.manager import TransferManager


@dataclass(frozen=True)
class IncomingTelegramMessage:
    telegram_id: int
    text: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class DialogService:
    def __init__(
        self,
        users: UsersRepository | InMemoryUsersRepository,
        messages: MessagesRepository | InMemoryMessagesRepository,
        events: EventsRepository | InMemoryEventsRepository,
        leads: LeadsRepository | InMemoryLeadsRepository,
        state_repo: InMemoryDialogStateRepository | None = None,
        classifier: IntentClassifier | None = None,
        transfer_manager: TransferManager | None = None,
        ai_chat: AIChatService | None = None,
        rate_limiter: InMemoryRateLimiter | None = None,
    ) -> None:
        self.users = users
        self.messages = messages
        self.events = events
        self.leads = leads
        self.engine = DialogEngine(messages, state_repo or InMemoryDialogStateRepository(), leads)
        self.classifier = classifier or IntentClassifier()
        self.transfer_manager = transfer_manager or TransferManager(users, leads, events, messages)
        self.ai_chat = ai_chat or AIChatService(messages, events)
        self.rate_limiter = rate_limiter or InMemoryRateLimiter()

    async def handle_telegram_text(self, incoming: IncomingTelegramMessage) -> str | None:
        rate = self.rate_limiter.check(incoming.telegram_id)
        if not rate.allowed:
            return "Пожалуйста, чуть медленнее. Я обрабатываю сообщения по очереди и сейчас отвечу по делу."

        user = await self.users.get_or_create(
            UserCreate(
                telegram_id=incoming.telegram_id,
                telegram_username=incoming.username,
                first_name=incoming.first_name,
                last_name=incoming.last_name,
            )
        )
        await self.events.save(
            EventCreate(
                user_id=user.id,
                event_type="message_received",
                event_data={"telegram_id": incoming.telegram_id, "text": incoming.text},
            )
        )
        await self.messages.save(
            MessageCreate(user_id=user.id, role=MessageRole.USER, content=incoming.text)
        )

        if user.is_silent:
            if should_reactivate_ai(incoming.text, user.silent_since):
                await self.users.set_silent(user.id, False)
                user = user.model_copy(update={"is_silent": False, "silent_since": None})
                await self.events.save(
                    EventCreate(
                        user_id=user.id,
                        event_type="ai_reactivated_by_client",
                        event_data={"text": incoming.text},
                    )
                )
            else:
                await self.events.save(
                    EventCreate(
                        user_id=user.id,
                        event_type="message_ignored_silent",
                        event_data={"text": incoming.text},
                    )
                )
                return None

        if not await is_ai_enabled():
            reply = "AI-ассистент сейчас временно отключен. Я передам сообщение менеджеру, он вернется с ответом."
            await self.events.save(
                EventCreate(user_id=user.id, event_type="ai_disabled_reply", event_data={"reply": reply})
            )
            return reply

        intent = await self.classifier.classify(incoming.text)
        await self.events.save(
            EventCreate(
                user_id=user.id,
                event_type="intent_classified",
                event_data={
                    "intent": intent.intent,
                    "sentiment": intent.sentiment,
                    "urgency": intent.urgency,
                    "confidence": intent.confidence,
                },
            )
        )

        routed = await self._handle_fast_route(user_id=user.id, intent=intent.intent)
        if routed:
            await self.events.save(
                EventCreate(user_id=user.id, event_type="message_replied", event_data={"reply": routed})
            )
            return routed

        history = await self.messages.last_n(user.id, n=15)
        context = await self._build_context(user.id)
        reply = await self.ai_chat.run(user=user, history=history, context=context)
        if not reply:
            reply = await self.engine.handle_text(user, incoming.text, save_user_message=False)
        await self.events.save(
            EventCreate(user_id=user.id, event_type="message_replied", event_data={"reply": reply})
        )
        return reply

    async def _build_context(self, user_id) -> str:
        lead = await self.leads.get_active_by_user_id(user_id)
        return (
            "КОНТЕКСТ КЛИЕНТА:\n"
            f"- Активный лид: {lead.model_dump(mode='json') if lead else 'нет'}\n"
            "- Если данных мало, задавай один следующий вопрос, а не анкету.\n"
        )

    async def _handle_fast_route(self, user_id, intent: str) -> str | None:
        if intent == "off_topic":
            return "Я помогаю по недвижимости: подобрать объект, подготовить продажу, анализ рынка или текст объявления. Что нужно?"

        if intent in {"legal_question", "complaint", "human_request"}:
            reason_map = {
                "legal_question": "legal_question",
                "complaint": "complaint",
                "human_request": "human_request",
            }
            await self.transfer_manager.transfer(
                user_id=user_id,
                reason=reason_map[intent],
                summary=f"Автоматическая передача менеджеру. Причина: {reason_map[intent]}",
            )
            await self.events.save(
                EventCreate(
                    user_id=user_id,
                    event_type="transfer_to_manager_required",
                    event_data={"reason": reason_map[intent]},
                )
            )
            return "Передаю ваш запрос менеджеру - он свяжется с вами и поможет дальше."

        return None


def create_in_memory_dialog_service() -> DialogService:
    return DialogService(
        users=InMemoryUsersRepository(),
        messages=InMemoryMessagesRepository(),
        events=InMemoryEventsRepository(),
        leads=InMemoryLeadsRepository(),
    )


def should_reactivate_ai(text: str, silent_since: datetime | None = None) -> bool:
    normalized = text.lower().replace("ё", "е").strip()
    reactivation_words = [
        "привет",
        "здравствуйте",
        "вернулся",
        "новый",
        "новое",
        "еще",
        "подобрать",
        "нужен",
        "нужно",
        "ищу",
        "хочу",
        "вариант",
        "объект",
        "квартира",
        "дом",
        "коммер",
    ]
    if any(word in normalized for word in reactivation_words):
        return True
    if silent_since:
        now = datetime.now(timezone.utc)
        if silent_since.tzinfo is None:
            silent_since = silent_since.replace(tzinfo=timezone.utc)
        if (now - silent_since).total_seconds() >= 10 * 60:
            return True
    return False
