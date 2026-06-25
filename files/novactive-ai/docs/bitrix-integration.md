# Интеграция с Битрикс24

## Способ интеграции

Используем **входящий webhook** Битрикс24 — самый простой вариант для MVP, не требует регистрации приложения в Marketplace.

### Получение webhook URL

1. В Битрикс24: Приложения → Разработчикам → Другое → Входящий вебхук
2. Дать права: `crm` (Лиды, Сделки, Контакты, Дела), `user` (пользователи), `calendar` (опционально, для просмотров)
3. Скопировать URL вида: `https://novactive.bitrix24.ru/rest/1/abc123def456/`

Сохранить в `.env` как `BITRIX_WEBHOOK_URL`.

## Что отправляем в Битрикс

### 1. Создание лида при квалификации

Когда AI вызвал `save_lead` и есть как минимум имя/телефон + критерии — создаём лид (не сделку, лид — на холодных этапах).

```python
async def create_bitrix_lead(lead: Lead, user: User) -> int:
    fields = {
        "TITLE": f"AI-бот: {user.first_name or 'клиент'} — {lead.property_type} {lead.rooms or ''}",
        "NAME": user.first_name,
        "LAST_NAME": user.last_name,
        "PHONE": [{"VALUE": user.phone, "VALUE_TYPE": "MOBILE"}] if user.phone else [],
        "SOURCE_ID": "OTHER",
        "SOURCE_DESCRIPTION": f"Telegram AI-бот (@{user.telegram_username})",
        "COMMENTS": format_lead_comment(lead),
        "ASSIGNED_BY_ID": settings.BITRIX_DEFAULT_MANAGER_ID,
        # Кастомные поля (нужно создать в Битриксе через настройки CRM):
        "UF_CRM_PROPERTY_TYPE": lead.property_type,
        "UF_CRM_BUDGET_MIN": lead.price_min,
        "UF_CRM_BUDGET_MAX": lead.price_max,
        "UF_CRM_DISTRICTS": ",".join(lead.districts) if lead.districts else "",
        "UF_CRM_TIMELINE": lead.timeline,
        "UF_CRM_MORTGAGE": "Y" if lead.mortgage_needed else "N",
    }
    
    response = await httpx_client.post(
        f"{settings.BITRIX_WEBHOOK_URL}crm.lead.add.json",
        json={"fields": fields}
    )
    return response.json()["result"]
```

### 2. Передача в сделку при hand-off

Когда AI вызвал `transfer_to_manager` — конвертируем лид в сделку или создаём сделку напрямую, с пометкой срочности.

```python
async def transfer_to_manager_in_bitrix(
    lead: Lead, user: User, reason: str, urgency: str, summary: str
) -> int:
    fields = {
        "TITLE": f"[{urgency.upper()}] {reason}: {user.first_name or 'клиент'}",
        "CATEGORY_ID": settings.BITRIX_DEAL_CATEGORY_ID,
        "STAGE_ID": "NEW",
        "CONTACT_ID": await ensure_bitrix_contact(user),
        "OPPORTUNITY": lead.price_max or 0,
        "CURRENCY_ID": "RUB",
        "ASSIGNED_BY_ID": settings.BITRIX_DEFAULT_MANAGER_ID,
        "SOURCE_ID": "OTHER",
        "COMMENTS": f"СРОЧНОСТЬ: {urgency}\nПРИЧИНА: {reason}\n\nКРАТКО:\n{summary}\n\n{format_lead_comment(lead)}",
        "UF_CRM_AI_DIALOG_URL": f"https://your-admin.novactive.ru/dialogs/{user.id}",
    }
    
    response = await httpx_client.post(
        f"{settings.BITRIX_WEBHOOK_URL}crm.deal.add.json",
        json={"fields": fields}
    )
    deal_id = response.json()["result"]
    
    # Создаём дело-напоминание для срочных
    if urgency == "high":
        await create_urgent_activity(deal_id, user)
    
    return deal_id


async def create_urgent_activity(deal_id: int, user: User):
    """Срочное дело — позвонить в течение 15 минут"""
    await httpx_client.post(
        f"{settings.BITRIX_WEBHOOK_URL}crm.activity.add.json",
        json={
            "fields": {
                "OWNER_TYPE_ID": 2,  # Deal
                "OWNER_ID": deal_id,
                "TYPE_ID": 2,  # Call
                "SUBJECT": f"СРОЧНО: позвонить {user.first_name} (AI-бот передал)",
                "DESCRIPTION": "Клиент из Telegram AI-бота. Срочный запрос — связаться в ближайшие 15 минут.",
                "RESPONSIBLE_ID": settings.BITRIX_DEFAULT_MANAGER_ID,
                "START_TIME": datetime.now().isoformat(),
                "END_TIME": (datetime.now() + timedelta(minutes=15)).isoformat(),
                "PRIORITY": 3,  # high
                "COMMUNICATIONS": [
                    {"TYPE": "PHONE", "VALUE": user.phone}
                ] if user.phone else []
            }
        }
    )
```

### 3. Создание контакта (если нет)

```python
async def ensure_bitrix_contact(user: User) -> int:
    # Сначала ищем по телефону
    if user.phone:
        search = await httpx_client.post(
            f"{settings.BITRIX_WEBHOOK_URL}crm.duplicate.findbycomm.json",
            json={"entity_type": "CONTACT", "type": "PHONE", "values": [user.phone]}
        )
        existing = search.json().get("result", {}).get("CONTACT", [])
        if existing:
            return existing[0]
    
    # Создаём нового
    response = await httpx_client.post(
        f"{settings.BITRIX_WEBHOOK_URL}crm.contact.add.json",
        json={
            "fields": {
                "NAME": user.first_name,
                "LAST_NAME": user.last_name,
                "PHONE": [{"VALUE": user.phone, "VALUE_TYPE": "MOBILE"}] if user.phone else [],
                "SOURCE_ID": "OTHER",
                "SOURCE_DESCRIPTION": "Telegram AI-бот",
            }
        }
    )
    return response.json()["result"]
```

## Формат комментария к лиду

```python
def format_lead_comment(lead: Lead) -> str:
    lines = ["=== Данные от AI-бота ==="]
    if lead.property_type: lines.append(f"Тип: {lead.property_type}")
    if lead.rooms: lines.append(f"Комнат: {lead.rooms}")
    if lead.price_min or lead.price_max:
        lines.append(f"Бюджет: {lead.price_min or '?'} — {lead.price_max or '?'} руб")
    if lead.districts: lines.append(f"Районы: {', '.join(lead.districts)}")
    if lead.timeline: lines.append(f"Сроки: {lead.timeline}")
    if lead.purpose: lines.append(f"Цель: {lead.purpose}")
    if lead.mortgage_needed is not None:
        lines.append(f"Ипотека: {'нужна' if lead.mortgage_needed else 'не нужна'}")
    if lead.materinsky_capital:
        lines.append("⚠ Маткапитал")
    if lead.additional_notes:
        lines.append(f"Доп: {lead.additional_notes}")
    return "\n".join(lines)
```

## Кастомные поля в Битрикс24

Перед запуском создать в настройках CRM Битрикс кастомные поля для лида и сделки:

| Код | Название | Тип |
|-----|----------|-----|
| UF_CRM_PROPERTY_TYPE | Тип недвижимости | Строка |
| UF_CRM_BUDGET_MIN | Бюджет от | Число |
| UF_CRM_BUDGET_MAX | Бюджет до | Число |
| UF_CRM_DISTRICTS | Районы | Строка |
| UF_CRM_TIMELINE | Сроки покупки | Строка |
| UF_CRM_MORTGAGE | Ипотека | Y/N |
| UF_CRM_AI_DIALOG_URL | Ссылка на диалог с AI | Строка |
| UF_CRM_AI_SCORE | Скор от AI | Число |

## Обратный канал (от менеджера к боту)

Когда менеджер закрывает сделку или хочет «вернуть» клиента боту — нужен исходящий webhook из Битрикс на наш бэкенд.

В Битрикс: Приложения → Разработчикам → Исходящий вебхук
- URL: `https://your-bot.ru/api/bitrix/webhook`
- События: `ONCRMDEALUPDATE`, `ONCRMDEALADD`

Бэкенд получает событие, находит user_id по deal_id, снимает silent режим:

```python
@router.post("/api/bitrix/webhook")
async def bitrix_webhook(request: Request):
    data = await request.form()
    event = data.get("event")
    deal_id = int(data.get("data[FIELDS][ID]", 0))
    
    if event == "ONCRMDEALUPDATE":
        # Проверяем стадию сделки
        deal = await get_bitrix_deal(deal_id)
        if deal["STAGE_ID"] in ["LOSE", "WON"]:
            # Сделка закрыта — снимаем silent режим
            await user_repo.unset_silent_by_deal_id(deal_id)
    
    return {"ok": True}
```

## Обработка ошибок

- Битрикс может быть недоступен → ретраи с экспоненциальным backoff (3 попытки)
- При полном фейле — записываем в `events` таблицу `bitrix_sync_failed` и оповещаем админа
- Никогда не блокируем ответ пользователю из-за фейла Битрикса — это побочная операция
