from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.db.models import UserCreate
from app.db.repositories.users import UsersRepository

router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    if message.from_user:
        users = UsersRepository()
        user = await users.get_or_create(
            UserCreate(
                telegram_id=message.from_user.id,
                telegram_username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
            )
        )
        await users.set_silent(user.id, False)

    await message.answer(
        "Здравствуйте. Я Алиса, AI-ассистент Новактив. "
        "Помогу подобрать объект, подготовить продажу, сделать анализ рынка или написать текст объявления."
    )
