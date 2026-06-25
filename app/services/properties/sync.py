from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.db.client import get_supabase
from app.db.repositories.settings import SettingsRepository
from app.db.table_names import AI_PROPERTIES_TABLE
from app.services.properties.quickdeal import QuickDealOffer, parse_quickdeal_feed


logger = get_logger(__name__)


class QuickDealSyncService:
    async def sync(self) -> int:
        stored_feed_url = await SettingsRepository().get_str("quickdeal_feed_url")
        feed_url = stored_feed_url or settings.quickdeal_feed_url
        if not feed_url:
            logger.info("quickdeal_sync_skipped", reason="feed_url_not_configured")
            return 0

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
            site_urls = await fetch_site_urls(client)

        offers = parse_quickdeal_feed(response.content)
        rows = [offer_to_row(offer, site_urls.get(offer.qd_id)) for offer in offers]
        supabase = await get_supabase()

        batch_size = settings.quickdeal_sync_batch_size
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            await supabase.table(AI_PROPERTIES_TABLE).upsert(batch, on_conflict="id").execute()

        logger.info("quickdeal_sync_completed", offers=len(rows))
        return len(rows)


async def fetch_site_urls(client: httpx.AsyncClient) -> dict[str, str]:
    url = "https://novactiv.ru/wp-json/novactiv/v1/property-map"
    try:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("property_site_url_map_failed", error=str(exc))
        return {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, dict):
        return {}
    return {str(key): str(value) for key, value in items.items() if value}


def offer_to_row(offer: QuickDealOffer, site_url: str | None = None) -> dict:
    return {
        "id": offer.id,
        "source": "quickdeal",
        "title": offer.title,
        "price": offer.price,
        "area": offer.area,
        "rooms": offer.rooms,
        "district": offer.district,
        "address": offer.address,
        "description": offer.description,
        "url": site_url or offer.url,
        "status": offer.status,
        "raw_json": offer.raw_json,
    }
