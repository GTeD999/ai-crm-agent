from app.services.dialog_service import IncomingTelegramMessage, create_in_memory_dialog_service
from app.db.models import MessageRole


async def test_dialog_service_keeps_context_across_messages() -> None:
    service = create_in_memory_dialog_service()

    first = await service.handle_telegram_text(
        IncomingTelegramMessage(telegram_id=1, text="Здравствуйте", first_name="Богдан")
    )
    assert first is not None
    assert "чем помочь" in first.lower()

    second = await service.handle_telegram_text(
        IncomingTelegramMessage(telegram_id=1, text="Мне требуется подобрать объект")
    )
    assert second is not None
    assert "покупка или аренда" in second.lower()

    third = await service.handle_telegram_text(
        IncomingTelegramMessage(telegram_id=1, text="Покупка дома")
    )
    assert third is not None
    assert "покупка или аренда" not in third.lower()

    user = await service.users.get_by_telegram_id(1)
    messages = await service.messages.last_n(user.id, n=20)
    user_messages = [message for message in messages if message.role == MessageRole.USER]
    assert [message.content for message in user_messages] == [
        "Здравствуйте",
        "Мне требуется подобрать объект",
        "Покупка дома",
    ]


async def test_premium_budget_goes_to_manager() -> None:
    service = create_in_memory_dialog_service()

    reply = await service.handle_telegram_text(
        IncomingTelegramMessage(telegram_id=2, text="Ищу дом до 100 млн рублей")
    )

    assert reply is not None
    assert "премиальный запрос" in reply.lower()
    assert "менеджер" in reply.lower()
