from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.db.repositories.followups import FollowupsRepository, InMemoryFollowupsRepository
from app.db.repositories.users import InMemoryUsersRepository, UsersRepository


SendMessage = Callable[[int, str], Awaitable[None]]


class FollowupJobs:
    def __init__(
        self,
        followups: FollowupsRepository | InMemoryFollowupsRepository | None = None,
        users: UsersRepository | InMemoryUsersRepository | None = None,
        send_message: SendMessage | None = None,
    ) -> None:
        self.followups = followups or FollowupsRepository()
        self.users = users or UsersRepository()
        self.send_message = send_message

    async def run_due(self) -> int:
        if not self.send_message:
            return 0
        sent = 0
        for followup in await self.followups.due():
            try:
                user = await self.users.get_by_id(followup.user_id)
                if not user or user.is_silent:
                    continue
                await self.send_message(user.telegram_id, followup.message or default_followup_text(followup.step))
                await self.followups.mark_sent(followup.id)
                sent += 1
            except Exception:
                await self.followups.mark_failed(followup.id)
        return sent


def default_followup_text(step: int) -> str:
    if step == 1:
        return "Здравствуйте. Подскажите, поиск ещё актуален? Могу продолжить подбор по вашим критериям."
    if step == 2:
        return "Добрый день. Хотите, проверю свежие варианты и подскажу, что появилось по вашему запросу?"
    return "Здравствуйте. Продолжаем поиск или заявку пока закрываем?"
