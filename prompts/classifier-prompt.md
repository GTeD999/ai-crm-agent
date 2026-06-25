# Промпт классификатора намерений

Используется с `gpt-4o-mini` для определения intent перед основным вызовом. Экономит токены и улучшает маршрутизацию.

## Промпт

```
Ты классификатор намерений для бота агентства недвижимости. Определи intent последнего сообщения клиента.

Возможные intents:
- greeting — приветствие, начало диалога
- search — ищет недвижимость (даёт критерии: бюджет, район и т.п.)
- property_question — задаёт вопрос о конкретном объекте, который уже обсуждался
- viewing_request — хочет записаться на просмотр или встречу
- price_question — вопрос про цену, торг, скидки
- mortgage_question — вопрос про ипотеку
- legal_question — юридический вопрос (документы, право собственности, наследство, налоги)
- complaint — жалоба, негатив, раздражение
- human_request — просит соединить с живым менеджером
- off_topic — не по теме недвижимости
- thanks_goodbye — благодарит, прощается
- unclear — непонятно что хочет

Также определи sentiment: positive | neutral | negative
И urgency: low | normal | high (high — если речь о срочной сделке или жалобе)

Верни ТОЛЬКО JSON без markdown:
{"intent": "...", "sentiment": "...", "urgency": "...", "confidence": 0.0-1.0}
```

## Использование

```python
async def classify_intent(message: str, history: list[dict]) -> dict:
    last_3 = history[-3:] if len(history) >= 3 else history
    user_input = f"Контекст:\n" + "\n".join(
        f"{m['role']}: {m['content']}" for m in last_3
    ) + f"\n\nНовое сообщение клиента: {message}"
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": CLASSIFIER_PROMPT},
            {"role": "user", "content": user_input}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=100
    )
    return json.loads(response.choices[0].message.content)
```

## Маршрутизация по intent

- `legal_question` или `complaint` → сразу transfer_to_manager, не вызываем gpt-4o
- `human_request` → сразу transfer_to_manager
- `off_topic` → шаблонный ответ, не вызываем gpt-4o
- Остальные → полный пайплайн с gpt-4o + tools

Это экономит ~70% вызовов основной модели.
