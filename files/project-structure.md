# Структура кода

```
novactive-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI + aiogram entrypoint
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # pydantic Settings
│   │   ├── logging.py             # structlog
│   │   └── exceptions.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── telegram_webhook.py    # POST /api/telegram/webhook
│   │   ├── bitrix_webhook.py      # POST /api/bitrix/webhook
│   │   └── health.py
│   │
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── dispatcher.py          # aiogram Dispatcher
│   │   ├── handlers/
│   │   │   ├── start.py           # /start, приветствие
│   │   │   ├── message.py         # обычные текстовые сообщения
│   │   │   └── consent.py         # обработка согласия на ПД
│   │   ├── keyboards.py           # inline keyboards (например для согласия)
│   │   └── middlewares.py         # rate limiting, user fetcher
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ai/
│   │   │   ├── client.py          # OpenAI клиент
│   │   │   ├── prompts.py         # загрузка промптов из prompts/
│   │   │   ├── tools.py           # dispatcher для tool calls
│   │   │   ├── classifier.py      # классификация intent
│   │   │   ├── extractor.py       # извлечение данных лида
│   │   │   ├── summarizer.py      # сжатие старой истории
│   │   │   └── embeddings.py      # генерация эмбеддингов
│   │   ├── properties/
│   │   │   ├── search.py          # search_properties tool
│   │   │   └── details.py         # get_property_details tool
│   │   ├── knowledge/
│   │   │   └── search.py          # search_knowledge_base tool
│   │   ├── leads/
│   │   │   ├── scoring.py         # подсчёт скора лида
│   │   │   └── save.py            # save_lead tool
│   │   ├── viewings/
│   │   │   └── booking.py         # book_viewing tool
│   │   ├── crm/
│   │   │   ├── bitrix_client.py   # httpx обёртка
│   │   │   ├── leads.py           # crm.lead.add
│   │   │   ├── deals.py           # crm.deal.add
│   │   │   └── contacts.py        # crm.contact.add
│   │   ├── consent/
│   │   │   └── manager.py         # request/confirm_pd_consent tools
│   │   ├── transfer/
│   │   │   └── manager.py         # transfer_to_manager tool
│   │   └── scheduler/
│   │       ├── apscheduler.py     # инициализация
│   │       └── followup_jobs.py   # задачи follow-up
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── client.py              # Supabase client
│   │   ├── models.py              # pydantic модели (User, Lead, Property, ...)
│   │   └── repositories/
│   │       ├── users.py
│   │       ├── messages.py
│   │       ├── leads.py
│   │       ├── properties.py
│   │       ├── viewings.py
│   │       ├── followups.py
│   │       └── events.py
│   │
│   └── utils/
│       ├── phone.py               # нормализация телефонов
│       ├── datetime.py            # МСК таймзона, парсинг дат
│       └── retry.py               # ретраи для внешних API
│
├── prompts/                       # копия markdown промптов из спецификации
├── schemas/                       # database.sql, openai-tools.json, lead-output.json
├── scripts/
│   ├── seed_properties.py         # загрузка объектов из CSV/Excel в БД
│   ├── generate_embeddings.py     # пересчёт эмбеддингов для объектов
│   └── seed_knowledge.py          # загрузка базы знаний
│
├── tests/
│   ├── conftest.py
│   ├── test_intent_classifier.py
│   ├── test_lead_extractor.py
│   ├── test_property_search.py
│   ├── test_bitrix_integration.py
│   └── e2e/
│       ├── test_full_dialog.py    # эмуляция диалогов
│       └── scenarios/             # YAML сценарии
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── .env.example
├── pyproject.toml                 # poetry или uv
├── requirements.txt
└── README.md
```

## Ключевые принципы реализации

### Асинхронность везде
Всё ввод/вывод — async: aiogram, httpx, supabase-py (async client), openai (AsyncOpenAI).

### Pydantic модели для всего
- Settings (config)
- Модели БД (валидация входа/выхода)
- Аргументы tools (валидация перед вызовом)
- Ответы Битрикс (опционально)

### Слои
1. **Handlers** (aiogram) — только тонкая обвязка. Получили сообщение → передали в сервис → отправили ответ.
2. **Services** — вся бизнес-логика. Не знают про Telegram или FastAPI.
3. **Repositories** — только доступ к БД, никакой логики.
4. **Clients** — внешние API (OpenAI, Битрикс).

### Tools dispatcher
Один словарь `name → callable` в `services/ai/tools.py`. Каждая функция принимает kwargs из tool_call и `user: User`, возвращает str/dict для отправки обратно в OpenAI.

```python
TOOLS_REGISTRY = {
    "search_properties": search_properties_tool,
    "get_property_details": get_property_details_tool,
    "search_knowledge_base": search_knowledge_tool,
    "save_lead": save_lead_tool,
    "book_viewing": book_viewing_tool,
    "request_pd_consent": request_consent_tool,
    "confirm_pd_consent": confirm_consent_tool,
    "transfer_to_manager": transfer_to_manager_tool,
}

async def dispatch_tool(name: str, args: dict, user: User) -> str:
    handler = TOOLS_REGISTRY[name]
    return await handler(**args, user=user)
```

### Цикл диалога (упрощённо)

```python
async def handle_user_message(user: User, text: str) -> str:
    # 1. Если бот в silent режиме — молчим
    if user.is_silent:
        return None  # не отвечаем
    
    # 2. Сохраняем сообщение
    await messages_repo.save(user.id, role="user", content=text)
    
    # 3. Классифицируем intent
    history = await messages_repo.last_n(user.id, n=5)
    intent = await classify_intent(text, history)
    
    # 4. Быстрые маршруты без вызова gpt-4o
    if intent["intent"] == "off_topic":
        return "Я помогаю подобрать недвижимость. Что ищете?"
    
    # 5. Полный пайплайн
    messages = await build_messages(user, intent)
    response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=TOOLS_SCHEMA,
        temperature=0.5
    )
    
    # 6. Обрабатываем tool_calls итеративно (макс 5 итераций)
    for _ in range(5):
        msg = response.choices[0].message
        if not msg.tool_calls:
            break
        tool_results = await execute_tools(msg.tool_calls, user)
        messages.append(msg.model_dump())
        messages.extend(tool_results)
        response = await openai_client.chat.completions.create(
            model="gpt-4o", messages=messages, tools=TOOLS_SCHEMA
        )
    
    # 7. Сохраняем ответ
    final_text = response.choices[0].message.content
    await messages_repo.save(user.id, role="assistant", content=final_text)
    
    # 8. Асинхронно обновляем лида (extract + score)
    asyncio.create_task(update_lead_data(user.id))
    
    return final_text
```

## Этапы реализации (для Codex)

1. **Основа** (день 1-2)
   - Структура проекта, config, logging
   - Supabase client + модели + репозитории users/messages
   - aiogram dispatcher + базовый /start
   - Healthcheck

2. **AI ядро** (день 3-4)
   - OpenAI клиент
   - Classifier
   - Базовый диалог без tools
   - Сохранение истории

3. **Tools часть 1** (день 5-6)
   - request/confirm_pd_consent
   - save_lead
   - extractor (фоновое обновление лида)

4. **Tools часть 2** (день 7-9)
   - Загрузка объектов в БД (seed_properties.py)
   - Генерация эмбеддингов
   - search_properties + get_property_details
   - search_knowledge_base

5. **Битрикс** (день 10-11)
   - Bitrix client
   - transfer_to_manager
   - Webhook от Битрикс для silent режима

6. **Просмотры + follow-up** (день 12-13)
   - book_viewing
   - APScheduler + follow-up jobs

7. **Тесты + деплой** (день 14)
   - E2E сценарии
   - Docker
   - Деплой на VPS
