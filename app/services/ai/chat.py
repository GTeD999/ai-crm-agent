from __future__ import annotations

import json

from openai import OpenAIError

from app.core.config import settings
from app.db.models import EventCreate, Message, MessageCreate, MessageRole, User
from app.db.repositories.events import EventsRepository, InMemoryEventsRepository
from app.db.repositories.messages import InMemoryMessagesRepository, MessagesRepository
from app.services.ai.client import openai_factory
from app.services.ai.prompts import load_prompt, load_schema
from app.services.ai.tools import ToolsDispatcher


class AIChatService:
    def __init__(
        self,
        messages_repo: MessagesRepository | InMemoryMessagesRepository,
        events_repo: EventsRepository | InMemoryEventsRepository,
        tools: ToolsDispatcher | None = None,
    ) -> None:
        self.messages_repo = messages_repo
        self.events_repo = events_repo
        self.tools = tools or ToolsDispatcher()

    async def run(self, user: User, history: list[Message], context: str = "") -> str | None:
        client = openai_factory.get()
        if not client:
            return None

        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "system", "content": context},
            *[
                {"role": message.role.value, "content": message.content}
                for message in history[-settings.max_context_messages :]
                if message.role in {MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM}
            ],
        ]
        tools_schema = load_schema("openai-tools.json")
        last_property_search: tuple[dict, dict] | None = None

        for _ in range(settings.max_tool_iterations):
            try:
                response = await client.chat.completions.create(
                    model=settings.openai_model_main,
                    messages=messages,
                    tools=tools_schema,
                    temperature=0.5,
                )
            except OpenAIError:
                if last_property_search:
                    result, args = last_property_search
                    reply = format_property_search_reply(result, args)
                    await self.messages_repo.save(
                        MessageCreate(
                            user_id=user.id,
                            role=MessageRole.ASSISTANT,
                            content=reply,
                            model="fallback-property-reply",
                        )
                    )
                    return reply
                raise

            choice = response.choices[0].message
            if not choice.tool_calls:
                content = choice.content or ""
                await self.messages_repo.save(
                    MessageCreate(
                        user_id=user.id,
                        role=MessageRole.ASSISTANT,
                        content=content,
                        tokens_input=response.usage.prompt_tokens if response.usage else None,
                        tokens_output=response.usage.completion_tokens if response.usage else None,
                        model=settings.openai_model_main,
                    )
                )
                return content

            assistant_message = choice.model_dump(exclude_none=True)
            messages.append(assistant_message)
            await self.messages_repo.save(
                MessageCreate(
                    user_id=user.id,
                    role=MessageRole.ASSISTANT,
                    content=choice.content or "",
                    tool_calls=[tool.model_dump() for tool in choice.tool_calls],
                    model=settings.openai_model_main,
                )
            )

            for tool_call in choice.tool_calls:
                args = json.loads(tool_call.function.arguments or "{}")
                result = await self.tools.dispatch(tool_call.function.name, args, user)
                await self.events_repo.save(
                    EventCreate(
                        user_id=user.id,
                        event_type="tool_called",
                        event_data={"name": tool_call.function.name, "args": args, "result": result},
                    )
                )
                tool_content = json.dumps(result, ensure_ascii=False)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": tool_content,
                    }
                )
                await self.messages_repo.save(
                    MessageCreate(
                        user_id=user.id,
                        role=MessageRole.TOOL,
                        content=tool_content,
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.function.name,
                    )
                )
                if tool_call.function.name == "search_properties":
                    last_property_search = (result, args)

        await self.events_repo.save(
            EventCreate(user_id=user.id, event_type="tool_iterations_exceeded", event_data={})
        )
        return "Проверяю информацию и передам запрос менеджеру, чтобы не дать вам неточные данные."


def build_system_prompt() -> str:
    prompt = load_prompt("system-prompt.md")
    return (
        prompt.replace("[ГОРОД]", settings.agency_city)
        .replace("[СПИСОК БАНКОВ]", settings.mortgage_partners or "уточняются")
        .replace("[ТЕЛЕФОН]", settings.agency_phone or "уточняется")
    )


def format_property_search_reply(result: dict, args: dict) -> str | None:
    if not result.get("ok"):
        return "Не смог сейчас проверить базу объектов. Передам запрос менеджеру, чтобы не оставить вас без подбора."

    properties = result.get("properties") or []
    property_label = property_type_label(args.get("property_type"))
    city = args.get("city") or settings.agency_city
    budget = format_price(args.get("price_max")) if args.get("price_max") else None

    if not properties:
        scope = f"{property_label}, город {city}"
        if budget:
            scope += f" до {budget}"
        return f"По текущей базе не нашел подходящие варианты: {scope}. Могу расширить район, бюджет или тип объекта."

    header = f"Нашел варианты: {property_label}, город {city}"
    if budget:
        header += f" до {budget}"
    lines = [header.rstrip(".") + "."]

    for index, item in enumerate(properties[:3], start=1):
        title = item.get("title") or "Объект"
        price = format_price(item.get("price"))
        address = ", ".join(part for part in [item.get("address"), item.get("district")] if part)
        area = f"{item.get('total_area'):g} м2" if isinstance(item.get("total_area"), int | float) else None
        url = item.get("site_url")
        lines.append("")
        lines.append(f"{index}. {title}")
        if address:
            lines.append(f"Адрес: {address}")
        details = [part for part in [price, area] if part]
        if details:
            lines.append("Параметры: " + " | ".join(details))
        if url:
            lines.append(f"Ссылка: {url}")

    lines.append("")
    lines.append("Какой вариант посмотреть подробнее или сузим подбор по району/площади?")
    return "\n".join(lines)


def property_type_label(value: str | None) -> str:
    labels = {
        "apartment": "квартиры",
        "house": "дома",
        "commercial": "коммерческие объекты",
        "land": "участки",
    }
    return labels.get(value or "", "объекты")


def format_price(value: int | float | str | None) -> str | None:
    if value is None:
        return None
    try:
        amount = int(float(value))
    except (TypeError, ValueError):
        return str(value)
    if amount >= 1_000_000:
        millions = amount / 1_000_000
        return f"{millions:g} млн руб."
    return f"{amount:,} руб.".replace(",", " ")
