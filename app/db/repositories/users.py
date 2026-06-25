from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.core.exceptions import RepositoryError
from app.db.client import get_supabase
from app.db.models import User, UserCreate
from app.db.table_names import AI_USERS_TABLE


class UsersRepository:
    async def get_by_id(self, user_id: UUID) -> User | None:
        client = await get_supabase()
        response = (
            await client.table(AI_USERS_TABLE)
            .select("*")
            .eq("id", str(user_id))
            .limit(1)
            .execute()
        )
        return User.model_validate(response.data[0]) if response and response.data else None

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        client = await get_supabase()
        response = (
            await client.table(AI_USERS_TABLE)
            .select("*")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
        return User.model_validate(response.data[0]) if response and response.data else None

    async def get_or_create(self, data: UserCreate) -> User:
        existing = await self.get_by_telegram_id(data.telegram_id)
        if existing:
            await self.touch(existing.id)
            return existing

        client = await get_supabase()
        response = (
            await client.table(AI_USERS_TABLE)
            .insert(
                {
                    "telegram_id": data.telegram_id,
                    "telegram_username": data.telegram_username,
                    "first_name": data.first_name,
                    "last_name": data.last_name,
                }
            )
            .execute()
        )
        if not response.data:
            raise RepositoryError("Failed to create user")
        return User.model_validate(response.data[0])

    async def touch(self, user_id: UUID) -> None:
        client = await get_supabase()
        await (
            client.table(AI_USERS_TABLE)
            .update({"last_message_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(user_id))
            .execute()
        )

    async def set_silent(self, user_id: UUID, is_silent: bool) -> None:
        client = await get_supabase()
        await (
            client.table(AI_USERS_TABLE)
            .update(
                {
                    "is_silent": is_silent,
                    "silent_since": datetime.now(timezone.utc).isoformat() if is_silent else None,
                }
            )
            .eq("id", str(user_id))
            .execute()
        )

    async def confirm_pd_consent(self, user_id: UUID) -> None:
        client = await get_supabase()
        await (
            client.table(AI_USERS_TABLE)
            .update({"pd_consent": True, "pd_consent_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", str(user_id))
            .execute()
        )

    async def set_phone(self, user_id: UUID, phone: str) -> None:
        client = await get_supabase()
        await client.table(AI_USERS_TABLE).update({"phone": phone}).eq("id", str(user_id)).execute()


class InMemoryUsersRepository:
    def __init__(self) -> None:
        self._users: dict[int, User] = {}

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return self._users.get(telegram_id)

    async def get_by_id(self, user_id: UUID) -> User | None:
        return next((user for user in self._users.values() if user.id == user_id), None)

    async def get_or_create(self, data: UserCreate) -> User:
        from uuid import uuid4

        existing = self._users.get(data.telegram_id)
        if existing:
            return existing
        now = datetime.now(timezone.utc)
        user = User(
            id=uuid4(),
            telegram_id=data.telegram_id,
            telegram_username=data.telegram_username,
            first_name=data.first_name,
            last_name=data.last_name,
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
        self._users[data.telegram_id] = user
        return user

    async def touch(self, user_id: UUID) -> None:
        return None

    async def set_silent(self, user_id: UUID, is_silent: bool) -> None:
        for telegram_id, user in self._users.items():
            if user.id == user_id:
                self._users[telegram_id] = user.model_copy(
                    update={
                        "is_silent": is_silent,
                        "silent_since": datetime.now(timezone.utc) if is_silent else None,
                    }
                )
                return

    async def confirm_pd_consent(self, user_id: UUID) -> None:
        for telegram_id, user in self._users.items():
            if user.id == user_id:
                self._users[telegram_id] = user.model_copy(
                    update={"pd_consent": True, "pd_consent_at": datetime.now(timezone.utc)}
                )
                return

    async def set_phone(self, user_id: UUID, phone: str) -> None:
        for telegram_id, user in self._users.items():
            if user.id == user_id:
                self._users[telegram_id] = user.model_copy(update={"phone": phone})
                return
