from __future__ import annotations

from dataclasses import dataclass
import json
import re

from app.core.config import settings
from app.services.ai.client import openai_factory
from app.services.ai.prompts import load_prompt


@dataclass(frozen=True)
class IntentResult:
    intent: str
    sentiment: str = "neutral"
    urgency: str = "normal"
    confidence: float = 0.8


class IntentClassifier:
    async def classify(self, text: str, history: list[str] | None = None) -> IntentResult:
        client = openai_factory.get()
        if not client:
            return classify_rule_based(text)

        try:
            prompt = extract_code_block(load_prompt("classifier-prompt.md"))
            context = "\n".join(history[-3:] if history else [])
            response = await client.chat.completions.create(
                model=settings.openai_model_fast,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": f"Контекст:\n{context}\n\nНовое сообщение клиента: {text}",
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=100,
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            return IntentResult(
                intent=str(payload.get("intent") or "unknown"),
                sentiment=str(payload.get("sentiment") or "neutral"),
                urgency=str(payload.get("urgency") or "normal"),
                confidence=float(payload.get("confidence") or 0.0),
            )
        except Exception:
            return classify_rule_based(text)


def classify_rule_based(text: str) -> IntentResult:
    normalized = text.lower().replace("ё", "е")

    if has_any(normalized, ["задолбали", "ужас", "жалоба", "нормальный человек", "плохой сервис"]):
        return IntentResult(intent="complaint", sentiment="negative", urgency="high", confidence=0.95)

    if has_any(normalized, ["юрист", "налог", "маткапитал", "наследство", "право собственности", "документ"]):
        return IntentResult(intent="legal_question", urgency="high", confidence=0.9)

    if has_any(normalized, ["менеджер", "живой человек", "соедините", "позвоните"]):
        return IntentResult(intent="human_request", urgency="high", confidence=0.9)

    price = extract_price(normalized)
    if price and price >= 20_000_000:
        return IntentResult(intent="premium_budget", urgency="high", confidence=0.88)

    if has_any(normalized, ["анализ рынка", "как продать", "стратегия продажи"]):
        return IntentResult(intent="market_analysis", confidence=0.85)

    if has_any(normalized, ["описание", "продающий текст", "пост", "креатив", "reels"]):
        return IntentResult(intent="copywriting", confidence=0.85)

    if has_any(normalized, ["купить", "покупка", "аренда", "снять", "подобрать", "объект", "дом", "квартира"]):
        return IntentResult(intent="property_request", confidence=0.8)

    if re.fullmatch(r"(привет|здравствуйте|добрый день|добрый вечер|доброе утро)[!. ]*", normalized):
        return IntentResult(intent="greeting", confidence=0.9)

    if has_any(normalized, ["погода", "рецепт", "политика", "философия"]):
        return IntentResult(intent="off_topic", confidence=0.9)

    return IntentResult(intent="unknown", confidence=0.4)


def has_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def extract_price(text: str) -> int | None:
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(млн|миллион|миллионов|тыс|тысяч)", text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    return int(value * (1_000 if match.group(2).startswith("тыс") else 1_000_000))


def extract_code_block(markdown: str) -> str:
    match = re.search(r"```(?:\w+)?\n(.*?)```", markdown, re.S)
    return match.group(1).strip() if match else markdown.strip()
