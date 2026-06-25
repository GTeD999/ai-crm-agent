from __future__ import annotations

import json

from app.core.config import settings
from app.db.models import LeadUpdate, Message
from app.services.ai.client import openai_factory
from app.services.ai.classifier import extract_code_block
from app.services.ai.prompts import load_prompt, load_schema


class LeadExtractor:
    async def extract(self, messages: list[Message]) -> LeadUpdate:
        fallback = extract_lead_rule_based("\n".join(message.content for message in messages))
        client = openai_factory.get()
        if not client:
            return fallback

        try:
            prompt = extract_code_block(load_prompt("lead-qualification-prompt.md"))
            schema = load_schema("lead-output.json")
            dialog = "\n".join(f"{message.role.value}: {message.content}" for message in messages)
            response = await client.chat.completions.create(
                model=settings.openai_model_fast,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Диалог:\n{dialog}"},
                ],
                response_format={"type": "json_schema", "json_schema": schema},
                temperature=0.0,
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            return LeadUpdate.model_validate({key: value for key, value in payload.items() if key not in {"name", "phone"}})
        except Exception:
            return fallback


def extract_lead_rule_based(text: str) -> LeadUpdate:
    import re

    normalized = text.lower().replace("ё", "е")
    property_type = None
    if re.search(r"дом|коттедж|таунхаус|особняк", normalized):
        property_type = "house"
    elif re.search(r"квартир|студи|однушк|двушк", normalized):
        property_type = "apartment"
    elif re.search(r"коммер|помещ|офис|склад", normalized):
        property_type = "commercial"
    elif re.search(r"участ|земл", normalized):
        property_type = "land"

    deal_type = "buy" if re.search(r"купить|покупк|приобр", normalized) else "rent" if re.search(r"аренд|снять", normalized) else None
    city = "Новосибирск" if "новосибирск" in normalized else None
    price_match = re.search(r"(?:до\s*)?(\d+(?:[,.]\d+)?)\s*(млн|миллион|миллионов|тыс|тысяч)", normalized)
    price_max = None
    if price_match:
        price_max = int(float(price_match.group(1).replace(",", ".")) * (1_000 if price_match.group(2).startswith("тыс") else 1_000_000))

    return LeadUpdate(property_type=property_type, deal_type=deal_type, city=city, price_max=price_max)
