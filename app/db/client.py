from __future__ import annotations

from collections.abc import AsyncIterator

from supabase import AsyncClient, create_async_client

from app.core.config import settings
from app.core.exceptions import RepositoryError


_client: AsyncClient | None = None


async def get_supabase() -> AsyncClient:
    global _client
    if _client is not None:
        return _client
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RepositoryError("Supabase URL and service key are required")
    _client = await create_async_client(settings.supabase_url, settings.supabase_service_key)
    return _client


async def lifespan_supabase() -> AsyncIterator[AsyncClient]:
    client = await get_supabase()
    yield client
