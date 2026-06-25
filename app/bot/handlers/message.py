from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.bot.keyboards import consent_keyboard, contact_keyboard
from app.db.models import UserCreate
from app.db.repositories.events import EventsRepository
from app.db.repositories.leads import LeadsRepository
from app.db.repositories.messages import MessagesRepository
from app.db.repositories.users import UsersRepository
from app.services.dialog_service import DialogService, IncomingTelegramMessage
from app.services.transfer.manager import TransferManager
from app.utils.phone import normalize_phone

router = Router()


@router.callback_query(F.data == "pd_consent:yes")
async def consent_callback(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return

    users = UsersRepository()
    leads = LeadsRepository()
    events = EventsRepository()
    messages = MessagesRepository()
    user = await users.get_or_create(
        UserCreate(
            telegram_id=callback.from_user.id,
            telegram_username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
    )
    await users.confirm_pd_consent(user.id)
    user = await users.get_by_id(user.id)
    await callback.answer("Согласие подтверждено")

    if not user or not user.phone:
        await callback.message.answer(
            "Спасибо. Теперь отправьте, пожалуйста, номер телефона кнопкой ниже.",
            reply_markup=contact_keyboard(),
        )
        return

    transfer = TransferManager(users, leads, events, messages)
    await transfer.transfer(
        user.id,
        reason="ready_to_close",
        summary="Клиент подтвердил согласие на обработку ПД и оставил телефон. Нужно связаться, уточнить интересующий объект и следующий шаг.",
        telegram=str(user.telegram_id),
    )
    await callback.message.answer(
        "Спасибо, контакт получил. Передаю ваши вводные специалисту, он свяжется и уточнит детали.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(F.contact)
async def contact_message(message: Message) -> None:
    if not message.from_user or not message.contact:
        return
    phone = normalize_phone(message.contact.phone_number)
    await handle_phone(message, phone)


@router.message()
async def text_message(message: Message) -> None:
    if not message.text or not message.from_user:
        return
    await message.bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)

    phone = extract_phone(message.text)
    if phone:
        await handle_phone(message, phone)
        return

    service = DialogService(
        users=UsersRepository(),
        messages=MessagesRepository(),
        events=EventsRepository(),
        leads=LeadsRepository(),
    )
    reply = await service.handle_telegram_text(
        IncomingTelegramMessage(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            text=message.text,
        )
    )
    if reply:
        await message.answer(reply)
        if should_offer_contact_button(reply):
            await message.answer("Можно отправить номер кнопкой ниже.", reply_markup=contact_keyboard())
        if should_offer_consent_button(reply):
            await message.answer(
                "Подтвердите согласие кнопкой ниже.",
                reply_markup=consent_keyboard(),
            )


async def handle_phone(message: Message, phone: str) -> None:
    users = UsersRepository()
    user = await users.get_or_create(
        UserCreate(
            telegram_id=message.from_user.id,
            telegram_username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
    )
    await users.set_phone(user.id, phone)
    user = await users.get_by_id(user.id)
    if user and user.pd_consent:
        leads = LeadsRepository()
        events = EventsRepository()
        messages = MessagesRepository()
        transfer = TransferManager(users, leads, events, messages)
        await transfer.transfer(
            user.id,
            reason="ready_to_close",
            summary="Клиент оставил телефон. Нужно связаться, уточнить интересующий объект и следующий шаг.",
            telegram=str(user.telegram_id),
        )
        await message.answer(
            "Спасибо, контакт получил. Передаю ваши вводные специалисту, он свяжется и уточнит детали.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await message.answer(
        "Спасибо, номер получил. Подтвердите, пожалуйста, согласие на обработку персональных данных.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Нажмите кнопку ниже, чтобы подтвердить согласие.", reply_markup=consent_keyboard())


def extract_phone(text: str) -> str | None:
    if not re.search(r"(?:\+7|8)\D*\d{3}\D*\d{3}\D*\d{2}\D*\d{2}", text):
        return None
    try:
        return normalize_phone(text)
    except ValueError:
        return None


def should_offer_contact_button(reply: str) -> bool:
    lower = reply.lower()
    return "номер" in lower or "телефон" in lower or "контакт" in lower


def should_offer_consent_button(reply: str) -> bool:
    lower = reply.lower()
    return "соглас" in lower or "персональ" in lower
