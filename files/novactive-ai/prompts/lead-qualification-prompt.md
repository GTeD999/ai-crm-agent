# Промпт извлечения данных лида

Запускается периодически (после каждых 3 сообщений клиента) на `gpt-4o-mini` для обновления структурированных данных лида в БД.

## Промпт

```
Ты извлекаешь структурированные данные о потребностях клиента из диалога с агентством недвижимости.

Проанализируй диалог и верни JSON с заполненными полями. Если поле не упомянуто или непонятно — оставь null. Не выдумывай.

Поля:
- property_type: "apartment" | "house" | "townhouse" | "commercial" | "land" | null
- deal_type: "buy" | "rent" | null
- new_or_secondary: "new" | "secondary" | "any" | null
- rooms: число комнат (1-5) или "studio", null если неясно
- price_min: число в рублях, null
- price_max: число в рублях, null
- area_min: метраж минимум в м², null
- area_max: метраж максимум в м², null
- districts: массив строк (районы города), [] если не упомянуто
- city: строка, null
- purpose: "live" | "invest" | "rent_out" | null
- timeline: "asap" | "1-3_months" | "3-6_months" | "6+_months" | null
- mortgage_needed: true | false | null
- has_first_payment: true | false | null
- first_payment_amount: число, null
- selling_other_property: true | false | null
- materinsky_capital: true | false | null
- name: имя клиента если назвал, null
- phone: телефон если дал, null
- additional_notes: строка с любыми дополнительными требованиями (этаж, ремонт, парковка, школы рядом и т.п.), null

Верни ТОЛЬКО JSON без markdown.
```

## JSON Schema (для structured output)

См. `schemas/lead-output.json` — там полная схема, которую можно передать в `response_format={"type": "json_schema", ...}` для гарантированной валидности.

## Использование

```python
async def extract_lead_data(messages: list[dict]) -> dict:
    dialog_text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": EXTRACTOR_PROMPT},
            {"role": "user", "content": f"Диалог:\n{dialog_text}"}
        ],
        response_format={
            "type": "json_schema",
            "json_schema": load_schema("lead-output.json")
        },
        temperature=0.0,
    )
    return json.loads(response.choices[0].message.content)
```

## Объединение с уже сохранёнными данными

При обновлении лида в БД мержим осторожно:
- Новые `null` поля **не затирают** существующие значения
- Числовые диапазоны (price_min/max) — заменяем целиком если есть новые
- Массивы (districts) — заменяем если новый непустой

```python
def merge_lead_data(existing: dict, new: dict) -> dict:
    merged = existing.copy()
    for key, value in new.items():
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        merged[key] = value
    return merged
```
