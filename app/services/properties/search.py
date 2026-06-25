from __future__ import annotations

from app.db.repositories.properties import InMemoryPropertiesRepository, PropertiesRepository
from app.services.properties.models import PropertyCard, PropertySearchArgs


class PropertySearchService:
    def __init__(self, repo: PropertiesRepository | InMemoryPropertiesRepository | None = None) -> None:
        self.repo = repo or PropertiesRepository()

    async def search_properties(self, args: PropertySearchArgs) -> list[PropertyCard]:
        return await self.repo.search(args)

    async def get_property_details(self, property_id: str) -> PropertyCard | None:
        return await self.repo.get_by_id(property_id)
