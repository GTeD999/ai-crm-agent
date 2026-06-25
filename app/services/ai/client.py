from __future__ import annotations

from openai import AsyncOpenAI

from app.core.config import settings


class OpenAIClientFactory:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def get(self) -> AsyncOpenAI | None:
        if not settings.openai_api_key:
            return None
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client


openai_factory = OpenAIClientFactory()

