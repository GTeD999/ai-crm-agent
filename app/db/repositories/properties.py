from __future__ import annotations

import re

from app.core.config import settings
from app.db.client import get_supabase
from app.db.table_names import AI_PROPERTIES_VIEW
from app.services.properties.models import PropertyCard, PropertySearchArgs


class PropertiesRepository:
    async def get_by_id(self, property_id: str) -> PropertyCard | None:
        client = await get_supabase()
        response = (
            await client.table(AI_PROPERTIES_VIEW)
            .select("*")
            .or_(f"id.eq.{property_id},external_id.eq.{property_id}")
            .limit(1)
            .execute()
        )
        return property_from_row(response.data[0]) if response and response.data else None

    async def search(self, args: PropertySearchArgs, limit: int = 5) -> list[PropertyCard]:
        client = await get_supabase()
        query = client.table(AI_PROPERTIES_VIEW).select("*").eq("status", "active").eq("deal_type", args.deal_type)

        if args.city:
            query = query.ilike("city", f"%{args.city}%")
        if args.property_type:
            query = query.eq("property_type", args.property_type)
        if args.price_min:
            query = query.gte("price", args.price_min)
        if args.price_max:
            query = query.lte("price", args.price_max)
        if args.area_min:
            query = query.gte("total_area", args.area_min)
        if args.area_max:
            query = query.lte("total_area", args.area_max)
        if args.rooms:
            query = query.in_("rooms", args.rooms)
        if args.districts:
            query = query.in_("district", args.districts)

        if args.price_max:
            query = query.order("price", desc=True)
        else:
            query = query.order("updated_at", desc=True)
        response = await query.limit(max(limit * 20, 100)).execute()
        properties = [property_from_row(row) for row in response.data or []]
        return rank_properties(properties, args)[:limit]


class InMemoryPropertiesRepository:
    def __init__(self, properties: list[PropertyCard] | None = None) -> None:
        self.properties = properties or []

    async def search(self, args: PropertySearchArgs, limit: int = 5) -> list[PropertyCard]:
        items = [
            item
            for item in self.properties
            if item.status == "active"
            if item.deal_type == args.deal_type
            and (not args.property_type or item.property_type == args.property_type)
            and (not args.city or args.city.lower() in item.city.lower())
            and (not args.districts or item.district in args.districts)
            and (not args.price_min or item.price >= args.price_min)
            and (not args.price_max or item.price <= args.price_max)
            and (not args.area_min or (item.total_area is not None and item.total_area >= args.area_min))
            and (not args.area_max or (item.total_area is not None and item.total_area <= args.area_max))
            and (not args.rooms or item.rooms in args.rooms)
        ]
        return rank_properties(items, args)[:limit]

    async def get_by_id(self, property_id: str) -> PropertyCard | None:
        return next((item for item in self.properties if str(item.id) == property_id), None)


def property_from_row(row: dict) -> PropertyCard:
    data = dict(row)
    data["site_url"] = data.get("site_url") or infer_site_url(data)
    return PropertyCard.model_validate(data)


def rank_properties(properties: list[PropertyCard], args: PropertySearchArgs) -> list[PropertyCard]:
    viable_properties = [item for item in properties if is_viable_property(item, args)]
    return sorted(
        viable_properties,
        key=lambda item: property_score(item, args),
        reverse=True,
    )


def is_viable_property(item: PropertyCard, args: PropertySearchArgs) -> bool:
    text = searchable_text(item)
    if item.price <= 1_000 and args.deal_type == "buy":
        return False
    if len(text) < 30:
        return False
    if re.search(r"\b(asd+|test|тест)\b", text, re.I):
        return False
    return True


def property_score(item: PropertyCard, args: PropertySearchArgs) -> float:
    score = 0.0
    query_tokens = tokenize(args.query_text or "")
    property_tokens = set(tokenize(searchable_text(item)))

    if query_tokens:
        matched = sum(1 for token in query_tokens if token in property_tokens)
        score += 180.0 * matched / len(set(query_tokens))

    if args.city and args.city.lower() in item.city.lower():
        score += 8.0
    if args.districts and item.district in args.districts:
        score += 14.0
    if args.property_type and item.property_type == args.property_type:
        score += 12.0
    if args.rooms and item.rooms in args.rooms:
        score += 10.0
    if args.area_min or args.area_max:
        score += range_fit(item.total_area, args.area_min, args.area_max, tolerance=0.2) * 10.0
    if args.price_min or args.price_max:
        score += range_fit(float(item.price), args.price_min, args.price_max, tolerance=0.15) * 14.0
    if args.price_max and not args.price_min:
        score += budget_closeness_score(item.price, args.price_max) * 180.0
        if item.price < args.price_max * 0.35:
            score -= 10.0
        if item.price < args.price_max * 0.1:
            score -= 25.0

    if item.photos:
        score += min(len(item.photos), 8) * 0.5
    if item.description:
        score += min(len(item.description), 1200) / 1200 * 4.0
    if item.site_url:
        score += 2.0

    return score


def range_fit(value: float | int | None, minimum: float | int | None, maximum: float | int | None, tolerance: float) -> float:
    if value is None:
        return 0.0
    min_value = float(minimum) if minimum is not None else None
    max_value = float(maximum) if maximum is not None else None
    if min_value is not None and value < min_value:
        return max(0.0, 1.0 - (min_value - value) / max(min_value * tolerance, 1.0))
    if max_value is not None and value > max_value:
        return max(0.0, 1.0 - (value - max_value) / max(max_value * tolerance, 1.0))
    if min_value is not None and max_value is not None and max_value > min_value:
        center = (min_value + max_value) / 2
        half_range = (max_value - min_value) / 2
        return 1.0 - min(abs(value - center) / max(half_range, 1.0), 0.4)
    if max_value is not None:
        return 1.0 - min(abs(max_value - value) / max(max_value, 1.0), 0.4)
    return 1.0


def budget_closeness_score(price: int, budget: int) -> float:
    if budget <= 0 or price <= 0 or price > budget:
        return 0.0
    ratio = price / budget
    return min(ratio, 1.0)


def searchable_text(item: PropertyCard) -> str:
    raw = item.raw_data or {}
    parts = [
        item.title,
        item.property_type,
        item.city,
        item.district,
        item.address,
        item.metro_station,
        item.renovation,
        item.description,
        " ".join(item.features or []),
        raw.get("commercial-type"),
        raw.get("property-type"),
        raw.get("search_text"),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def tokenize(value: str) -> list[str]:
    aliases = {
        "псн": "свободного назначения",
        "общепит": "кафе ресторан питание",
        "производство": "производственный manufacturing",
        "склад": "warehouse складской",
        "магазин": "retail торговля",
        "офис": "office офисный",
    }
    normalized = value.lower().replace("ё", "е")
    for source, replacement in aliases.items():
        normalized = normalized.replace(source, f"{source} {replacement}")
    tokens = re.findall(r"[a-zа-я0-9]{3,}", normalized)
    return [token for token in tokens if not token.isdigit()]


def infer_site_url(row: dict) -> str | None:
    for key in ("site_url", "url", "link", "permalink", "wordpress_url", "wp_url", "object_url"):
        value = row.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value

    raw_data = row.get("raw_data")
    if isinstance(raw_data, dict):
        for key in ("site_url", "url", "link", "permalink", "wordpress_url", "wp_url", "object_url"):
            value = raw_data.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        if raw_data.get("qd_id") and not raw_data.get("wordpress_id"):
            return None

    external_id = row.get("external_id")
    if isinstance(external_id, str) and external_id.isdigit():
        return f"{settings.property_site_base_url.rstrip('/')}/{external_id}/"
    return None
