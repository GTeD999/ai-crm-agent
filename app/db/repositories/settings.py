from __future__ import annotations

from app.core.exceptions import RepositoryError
from app.db.client import get_supabase
from app.db.table_names import AI_SETTINGS_TABLE


class SettingsRepository:
    async def get_value(self, key: str, default=None):
        try:
            client = await get_supabase()
            response = await client.table(AI_SETTINGS_TABLE).select("value").eq("key", key).limit(1).execute()
        except RepositoryError:
            return default
        if not response.data:
            return default
        return response.data[0].get("value", default)

    async def set_value(self, key: str, value) -> None:
        client = await get_supabase()
        await (
            client.table(AI_SETTINGS_TABLE)
            .upsert({"key": key, "value": value}, on_conflict="key")
            .execute()
        )

    async def get_bool(self, key: str, default: bool) -> bool:
        value = await self.get_value(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"true", "1", "yes", "on"}
        return default

    async def set_bool(self, key: str, value: bool) -> None:
        await self.set_value(key, value)

    async def get_str(self, key: str, default: str | None = None) -> str | None:
        value = await self.get_value(key, default)
        return value if isinstance(value, str) else default

    async def set_str(self, key: str, value: str) -> None:
        await self.set_value(key, value)


async def is_ai_enabled() -> bool:
    return await SettingsRepository().get_bool("ai_enabled", True)
