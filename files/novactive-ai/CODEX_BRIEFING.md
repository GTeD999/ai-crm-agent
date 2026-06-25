# 🤖 BRIEFING ДЛЯ CODEX

Этот документ — короткая инструкция, которую можно дать Codex в первом промпте. Все детали в остальных файлах пакета.

---

## Задача

Реализовать AI-менеджера для агентства недвижимости «Новактив». MVP — Telegram-бот, который квалифицирует лиды, ищет объекты в базе и передаёт «горячих» клиентов в Битрикс24.

## Стек

- Python 3.11+, FastAPI, aiogram 3.x
- OpenAI: gpt-4o (диалог), gpt-4o-mini (классификация/извлечение), text-embedding-3-small (RAG)
- Supabase (Postgres 15 + pgvector)
- Битрикс24 (входящий webhook)
- APScheduler для follow-up
- Docker для деплоя

## Что есть в пакете

| Файл | Что это |
|------|---------|
| `README.md` | Обзор проекта |
| `docs/architecture.md` | Архитектура, слои, потоки данных |
| `docs/bitrix-integration.md` | Готовый код интеграции с Битрикс24 |
| `docs/deployment.md` | Docker, Caddy, инструкции деплоя |
| `docs/testing.md` | 11 e2e-сценариев + edge cases |
| `prompts/system-prompt.md` | Главный системный промпт (готов, копировать как есть) |
| `prompts/classifier-prompt.md` | Промпт для классификации intent |
| `prompts/lead-qualification-prompt.md` | Промпт извлечения данных лида |
| `schemas/database.sql` | Полная схема БД для Supabase, включая RPC-функции |
| `schemas/openai-tools.json` | Все 8 tools для function calling |
| `schemas/lead-output.json` | JSON Schema для structured output |
| `code/project-structure.md` | Дерево проекта + цикл диалога в псевдокоде |
| `code/requirements.txt` | Зависимости |
| `code/env.example` | Все переменные окружения |

## Tools, которые умеет AI

1. `search_properties` — гибридный поиск (фильтры + векторное ранжирование)
2. `get_property_details` — детали объекта
3. `search_knowledge_base` — RAG по ипотеке/ЖК/FAQ
4. `save_lead` — сохранение/обновление данных клиента
5. `book_viewing` — запись на просмотр
6. `request_pd_consent` / `confirm_pd_consent` — согласие на 152-ФЗ
7. `transfer_to_manager` — эскалация в Битрикс24

## Порядок реализации

1. Проект, config, logging
2. Supabase подключение + модели + репозитории
3. aiogram dispatcher + /start + middlewares
4. OpenAI клиент + classifier
5. Базовый цикл диалога без tools
6. Tools: consent, save_lead, extractor
7. Загрузка объектов + эмбеддинги
8. Tools: search_properties, get_property_details, knowledge
9. Битрикс клиент + transfer_to_manager
10. book_viewing + APScheduler + follow-up
11. Webhook от Битрикс (silent mode)
12. Docker + деплой
13. E2E тесты

## Критичные требования

1. **Anti-hallucination**: AI никогда не выдумывает объекты, цены, метраж. Только данные из БД через tools.
2. **152-ФЗ**: согласие на обработку ПД до сохранения телефона/имени.
3. **Hand-off**: при передаче менеджеру → silent mode (бот молчит, пока менеджер не закроет сделку).
4. **Логирование**: все сообщения, tool calls, события — в БД (`messages`, `events`).
5. **Rate limiting**: 10 сообщений/мин на пользователя.
6. **Юридические вопросы** — только через менеджера, никогда не отвечает AI.
7. **Премиум-бюджет (от 20 млн)** — только через менеджера.

## Как давать задачи Codex

Не одним промптом на всё. Разбивать по модулям:

```
Прочитай весь пакет в папке officee-ai/. 
Реализуй модуль app/db/ (client, models, repositories для users и messages) 
согласно code/project-structure.md и schemas/database.sql.
Используй supabase-py async client и pydantic 2.x.
Напиши unit-тесты для репозиториев.
```

Потом:
```
Теперь реализуй app/services/ai/ — клиент OpenAI, classifier, базовый цикл диалога 
без tools, согласно prompts/classifier-prompt.md и code/project-structure.md.
```

И так далее по списку «Порядок реализации».

## Чего не делать

- Не использовать synchronous код для I/O (всё async)
- Не хранить весь контекст диалога в OpenAI (только последние 15 + summary)
- Не отвечать пользователю, если ошибка во внешнем API (например Битрикс) — логировать и продолжать
- Не делать tool без типизированных аргументов через pydantic
- Не игнорировать `user.is_silent` — это критичный флаг
- Не пытаться обработать tool_calls бесконечно — лимит 5 итераций

## Финальный чек-лист готовности

- [ ] Накатывается миграция БД одной командой
- [ ] Бот отвечает на /start приветствием
- [ ] Полный диалог с квалификацией работает (см. сценарий 1 в docs/testing.md)
- [ ] Лид создаётся в Битрикс24
- [ ] Hand-off работает: silent mode включается и снимается
- [ ] Follow-up отправляется через 24ч/3д/7д
- [ ] Все 11 e2e сценариев проходят
- [ ] Docker compose поднимает бота за одну команду
- [ ] Healthcheck зелёный
- [ ] Расход OpenAI < $0.05 на полный диалог квалификации
