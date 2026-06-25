from __future__ import annotations

from dataclasses import dataclass, field
import re
from uuid import UUID

from app.db.models import MessageCreate, MessageRole, User
from app.db.models import LeadStatus, LeadUpdate
from app.db.repositories.leads import InMemoryLeadsRepository, LeadsRepository
from app.db.repositories.messages import InMemoryMessagesRepository, MessagesRepository


@dataclass
class DialogState:
    mode: str = "unknown"  # buyer, seller, analyst, copywriter
    stage: str = "greeting"  # greeting, qualifying, ready_to_search, handoff
    property_type: str | None = None
    deal_type: str | None = None
    price_max: int | None = None
    city: str | None = None
    last_question: str | None = None
    notes: list[str] = field(default_factory=list)


class InMemoryDialogStateRepository:
    def __init__(self) -> None:
        self._state: dict[UUID, DialogState] = {}

    async def get(self, user_id: UUID) -> DialogState:
        return self._state.get(user_id, DialogState())

    async def save(self, user_id: UUID, state: DialogState) -> None:
        self._state[user_id] = state


class DialogEngine:
    """Deterministic dialog core for early e2e tests.

    This is intentionally not the final AI brain. It protects the project from
    the previous failure mode: losing state between turns. OpenAI/tools will sit
    on top of this explicit state, not replace it.
    """

    def __init__(
        self,
        messages_repo: MessagesRepository | InMemoryMessagesRepository,
        state_repo: InMemoryDialogStateRepository,
        leads_repo: LeadsRepository | InMemoryLeadsRepository | None = None,
    ) -> None:
        self.messages = messages_repo
        self.states = state_repo
        self.leads = leads_repo

    async def handle_text(self, user: User, text: str, save_user_message: bool = True) -> str | None:
        if user.is_silent:
            return None

        if save_user_message:
            await self.messages.save(
                MessageCreate(user_id=user.id, role=MessageRole.USER, content=text)
            )
        state = await self.states.get(user.id)
        state = self._update_state(state, text)
        if self.leads:
            await self.leads.upsert_for_user(user.id, state_to_lead_update(state))
        reply = self._reply_for_state(state, text)
        await self.states.save(user.id, state)
        await self.messages.save(
            MessageCreate(user_id=user.id, role=MessageRole.ASSISTANT, content=reply)
        )
        return reply

    def _update_state(self, state: DialogState, text: str) -> DialogState:
        normalized = normalize(text)

        if has_any(normalized, ["подобрать", "подорбать", "подбрать", "объект", "обьект", "опбьект"]):
            state.mode = "buyer"
            state.stage = "qualifying"

        if has_any(normalized, ["покупка", "купить", "покупаю"]):
            state.mode = "buyer"
            state.deal_type = "buy"
            state.stage = "qualifying"

        if has_any(normalized, ["дом", "коттедж", "таунхаус", "особняк"]):
            state.property_type = "house"
            state.mode = "buyer" if state.mode == "unknown" else state.mode
            state.stage = "qualifying"

        if has_any(normalized, ["квартира", "квартиру", "однушка", "двушка", "студия"]):
            state.property_type = "apartment"
            state.mode = "buyer" if state.mode == "unknown" else state.mode
            state.stage = "qualifying"

        if has_any(normalized, ["коммерция", "коммерческая", "помещение", "офис", "склад"]):
            state.property_type = "commercial"
            state.mode = "buyer" if state.mode == "unknown" else state.mode
            state.stage = "qualifying"

        if has_any(normalized, ["анализ", "рынок"]):
            state.mode = "analyst"
            state.stage = "qualifying"

        if has_any(normalized, ["описание", "текст", "пост", "креатив"]):
            state.mode = "copywriter"
            state.stage = "qualifying"

        if has_any(normalized, ["новосибирск", "новосибирске"]):
            state.city = "Новосибирск"

        price = extract_price_max(normalized)
        if price:
            state.price_max = price

        if state.price_max and state.price_max >= 20_000_000:
            state.stage = "handoff"

        if state.mode == "buyer" and state.deal_type and state.property_type and state.city and state.price_max:
            state.stage = "handoff" if state.price_max >= 20_000_000 else "ready_to_search"

        return state

    def _reply_for_state(self, state: DialogState, text: str) -> str:
        normalized = normalize(text)

        if is_greeting(normalized) and state.mode == "unknown":
            state.last_question = "task"
            return "Здравствуйте. Я на связи. Подскажите, чем помочь: подобрать объект, продать ваш объект, сделать анализ рынка или подготовить текст?"

        if state.mode == "analyst":
            return "Понял задачу по анализу рынка. Пришлите тип объекта, район, площадь и цену - соберу структуру продажи, конкурентов и позиционирование."

        if state.mode == "copywriter":
            return "Понял, подготовим текст. Пришлите тип объекта, локацию, площадь, цену и 3-5 сильных деталей - сделаю премиальное описание."

        if state.mode == "buyer":
            missing = []
            if not state.deal_type:
                missing.append("покупка или аренда")
            if not state.property_type:
                missing.append("тип объекта: квартира, дом, коммерция или участок")
            if not state.city:
                missing.append("город или район")
            if not state.price_max:
                missing.append("ориентир по бюджету")

            if state.stage == "handoff":
                return self._handoff_reply(state)

            if missing:
                state.last_question = ", ".join(missing[:2])
                return f"Хорошо, подберём. Уточните, пожалуйста: {state.last_question}."

            return "Понял критерии. Следующим шагом проверю базу и покажу только релевантные варианты, без подмены запроса."

        return "Понял. Уточните, пожалуйста, какая задача сейчас актуальна: подбор, продажа, анализ рынка или текст для объявления?"

    def _handoff_reply(self, state: DialogState) -> str:
        if state.price_max and state.price_max >= 20_000_000:
            return (
                "Понял: покупка дома с бюджетом до "
                f"{format_rub(state.price_max)}. Это премиальный запрос, такие заявки лучше сразу вести с менеджером. "
                "Передам вводные специалисту, чтобы он проверил актуальные варианты вручную."
            )
        return "Передам ваш запрос менеджеру - он подключится и поможет с точным подбором."


def normalize(text: str) -> str:
    return text.lower().replace("ё", "е").strip()


def has_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def is_greeting(text: str) -> bool:
    return bool(re.fullmatch(r"(здравствуйте|здравствуй|привет|добрый день|добрый вечер|доброе утро)[!. ]*", text))


def extract_price_max(text: str) -> int | None:
    match = re.search(r"(?:до\s*)?(\d+(?:[,.]\d+)?)\s*(млн|миллион|миллионов|тыс|тысяч)", text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    multiplier = 1_000 if match.group(2).startswith("тыс") else 1_000_000
    return int(value * multiplier)


def format_rub(value: int) -> str:
    if value >= 1_000_000:
        amount = value / 1_000_000
        return f"{amount:g} млн рублей"
    return f"{value:,} рублей".replace(",", " ")


def state_to_lead_update(state: DialogState) -> LeadUpdate:
    status = LeadStatus.HOT if state.stage == "handoff" else LeadStatus.QUALIFIED if state.stage == "ready_to_search" else LeadStatus.NEW
    return LeadUpdate(
        property_type=state.property_type,
        deal_type=state.deal_type,
        price_max=state.price_max,
        city=state.city,
        additional_notes="\n".join(state.notes) if state.notes else None,
        status=status,
        score=score_state(state),
    )


def score_state(state: DialogState) -> int:
    score = 0
    if state.mode != "unknown":
        score += 10
    if state.deal_type:
        score += 20
    if state.property_type:
        score += 20
    if state.city:
        score += 15
    if state.price_max:
        score += 20
    if state.stage == "handoff":
        score += 15
    return min(score, 100)
