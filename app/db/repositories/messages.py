from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from app.core.exceptions import RepositoryError
from app.db.client import get_supabase
from app.db.models import Message, MessageCreate, MessageRole
from app.db.table_names import AI_MESSAGES_TABLE


class MessagesRepository:
    async def save(self, data: MessageCreate) -> Message:
        client = await get_supabase()
        response = (
            await client.table(AI_MESSAGES_TABLE)
            .insert(
                {
                    "user_id": str(data.user_id),
                    "role": data.role.value,
                    "content": data.content,
                    "tool_calls": data.tool_calls,
                    "tool_call_id": data.tool_call_id,
                    "tool_name": data.tool_name,
                    "intent": data.intent,
                    "sentiment": data.sentiment,
                    "urgency": data.urgency,
                    "tokens_input": data.tokens_input,
                    "tokens_output": data.tokens_output,
                    "model": data.model,
                }
            )
            .execute()
        )
        if not response.data:
            raise RepositoryError("Failed to save message")
        return Message.model_validate(response.data[0])

    async def last_n(self, user_id: UUID, n: int = 15) -> list[Message]:
        client = await get_supabase()
        response = (
            await client.table(AI_MESSAGES_TABLE)
            .select("*")
            .eq("user_id", str(user_id))
            .order("created_at", desc=True)
            .limit(n)
            .execute()
        )
        return [Message.model_validate(row) for row in reversed(response.data or [])]


class InMemoryMessagesRepository:
    def __init__(self) -> None:
        self._messages: dict[UUID, list[Message]] = defaultdict(list)

    async def save(self, data: MessageCreate) -> Message:
        from datetime import datetime, timezone
        from uuid import uuid4

        message = Message(
            id=uuid4(),
            user_id=data.user_id,
            role=data.role,
            content=data.content,
            tool_calls=data.tool_calls,
            tool_call_id=data.tool_call_id,
            tool_name=data.tool_name,
            intent=data.intent,
            sentiment=data.sentiment,
            urgency=data.urgency,
            tokens_input=data.tokens_input,
            tokens_output=data.tokens_output,
            model=data.model,
            created_at=datetime.now(timezone.utc),
        )
        self._messages[data.user_id].append(message)
        return message

    async def last_n(self, user_id: UUID, n: int = 15) -> list[Message]:
        return self._messages[user_id][-n:]


def messages_to_openai(messages: list[Message]) -> list[dict[str, str]]:
    role_map = {
        MessageRole.USER: "user",
        MessageRole.ASSISTANT: "assistant",
        MessageRole.SYSTEM: "system",
        MessageRole.TOOL: "tool",
    }
    return [{"role": role_map[message.role], "content": message.content} for message in messages]
