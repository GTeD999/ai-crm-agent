from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
import xml.etree.ElementTree as ET


YANDEX_REALTY_NS = "http://webmaster.yandex.ru/schemas/feed/realty/2010-06"
NS = {"y": YANDEX_REALTY_NS}


@dataclass(frozen=True)
class QuickDealOffer:
    id: str
    qd_id: str
    title: str
    status: str
    price: int
    area: float | None
    rooms: int | None
    district: str | None
    address: str | None
    description: str
    url: str | None
    raw_json: dict


def parse_quickdeal_feed(xml_content: bytes | str) -> list[QuickDealOffer]:
    root = ET.fromstring(xml_content)
    return [
        offer
        for node in root.findall("y:offer", NS)
        if (offer := parse_offer(node)) is not None
    ]


def parse_offer(node: ET.Element) -> QuickDealOffer | None:
    internal_id = node.attrib.get("internal-id") or text(node, "qd_id")
    qd_id = text(node, "qd_id") or internal_id.removeprefix("QD_REALTY_")
    price = int_or_none(text(node, "price/value"))
    if not internal_id or not qd_id or not price:
        return None

    raw = offer_to_raw_json(node)
    description = strip_html(text(node, "description") or "")
    category = text(node, "category")
    commercial_type = text(node, "commercial-type")
    address = text(node, "location/address")
    area = float_or_none(text(node, "area/value"))
    rooms = int_or_none(text(node, "rooms"))
    title = text(node, "title") or build_title(category, commercial_type, area, address)

    return QuickDealOffer(
        id=qd_id,
        qd_id=qd_id,
        title=title,
        status="active",
        price=price,
        area=area,
        rooms=rooms,
        district=text(node, "location/sub-locality-name") or text(node, "location/district"),
        address=address,
        description=description,
        url=None,
        raw_json=raw,
    )


def offer_to_raw_json(node: ET.Element) -> dict:
    data = element_to_value(node)
    if not isinstance(data, dict):
        return {}
    data["internal_id"] = node.attrib.get("internal-id")
    data["deal_type"] = normalize_deal_type(data.get("type"))
    data["property_type"] = normalize_property_type(data.get("category"), data.get("commercial-type"))
    data["photos"] = [{"url": url} for url in values(data.get("image")) if isinstance(url, str)]
    data["search_text"] = build_search_text(data)
    return data


def element_to_value(element: ET.Element) -> str | dict | list | None:
    children = list(element)
    if not children:
        value = (element.text or "").strip()
        return value or None

    result: dict[str, object] = {}
    for child in children:
        key = child.tag.split("}", 1)[-1]
        value = element_to_value(child)
        if key in result:
            existing = result[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                result[key] = [existing, value]
        else:
            result[key] = value
    return result


def build_title(category: str | None, commercial_type: str | None, area: float | None, address: str | None) -> str:
    kind = category or commercial_type or "Объект недвижимости"
    area_part = f" {area:g} м²" if area else ""
    address_part = f", {address}" if address else ""
    return f"{kind.capitalize()}{area_part}{address_part}"


def build_search_text(data: dict) -> str:
    parts = [
        data.get("title"),
        data.get("category"),
        data.get("commercial-type"),
        data.get("property-type"),
        nested(data, "location", "locality-name"),
        nested(data, "location", "sub-locality-name"),
        nested(data, "location", "district"),
        nested(data, "location", "address"),
        data.get("renovation"),
        data.get("quality"),
        strip_html(str(data.get("description") or "")),
    ]
    return " ".join(str(part) for part in parts if part)


def normalize_deal_type(value: object) -> str:
    normalized = str(value or "").lower()
    if "аренд" in normalized or normalized in {"rent", "lease"}:
        return "rent"
    return "buy"


def normalize_property_type(category: object, commercial_type: object = None) -> str:
    normalized = f"{category or ''} {commercial_type or ''}".lower()
    if "участ" in normalized or "land" in normalized:
        return "land"
    if any(word in normalized for word in ("коммер", "office", "retail", "warehouse", "free purpose", "manufacturing", "business")):
        return "commercial"
    if any(word in normalized for word in ("коттедж", "дом", "дача")):
        return "house"
    if "таунхаус" in normalized:
        return "townhouse"
    if "комнат" in normalized:
        return "room"
    return "apartment"


def text(node: ET.Element, path: str) -> str | None:
    child = node.find(f"y:{path.replace('/', '/y:')}", NS)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def nested(data: dict, *path: str) -> object:
    current: object = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def values(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def strip_html(value: str) -> str:
    text_value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text_value = re.sub(r"<[^>]+>", " ", text_value)
    text_value = unescape(text_value)
    text_value = re.sub(r"\s+", " ", text_value)
    return text_value.strip()


def int_or_none(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(float(value.replace(",", ".")))
    except ValueError:
        return None


def float_or_none(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None
