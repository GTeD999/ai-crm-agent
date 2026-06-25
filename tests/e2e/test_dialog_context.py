from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.db.models import User
from app.db.repositories.messages import InMemoryMessagesRepository
from app.db.repositories.leads import InMemoryLeadsRepository
from app.services.ai.dialog_engine import DialogEngine, InMemoryDialogStateRepository


@pytest.fixture
def user() -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        telegram_id=123,
        first_name="Богдан",
        created_at=now,
        updated_at=now,
        last_message_at=now,
    )


@pytest.fixture
def engine() -> DialogEngine:
    return DialogEngine(InMemoryMessagesRepository(), InMemoryDialogStateRepository(), InMemoryLeadsRepository())


async def test_buyer_house_context_is_preserved(engine: DialogEngine, user: User) -> None:
    reply = await engine.handle_text(user, "Здравствуйте")
    assert "чем помочь" in reply.lower()

    reply = await engine.handle_text(user, "Мне требуется подорбать опбьект")
    assert "покупка или аренда" in reply.lower()

    reply = await engine.handle_text(user, "Покупка дома")
    assert "город" in reply.lower() or "район" in reply.lower()
    assert "покупка или аренда" not in reply.lower()

    reply = await engine.handle_text(user, "мне нужен дом до 100 млн рублей в Новосибирске")
    assert "премиальный запрос" in reply.lower()
    assert "квартир" not in reply.lower()


async def test_analysis_does_not_trigger_property_search(engine: DialogEngine, user: User) -> None:
    reply = await engine.handle_text(
        user,
        "Нужно сделать анализ рынка как продать коммерческий объект за 15 млн в Новосибирске",
    )
    assert "анализ" in reply.lower()
    assert "покажу" not in reply.lower()


async def test_copywriting_mode_is_separate(engine: DialogEngine, user: User) -> None:
    reply = await engine.handle_text(
        user,
        "Я продаю дом за 50 миллионов, нужно премиальное описание объекта",
    )
    assert "текст" in reply.lower() or "описание" in reply.lower()
    assert "подбер" not in reply.lower()
