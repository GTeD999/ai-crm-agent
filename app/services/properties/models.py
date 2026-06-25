from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PropertySearchArgs(BaseModel):
    query_text: str | None = None
    city: str | None = None
    districts: list[str] | None = None
    property_type: str | None = None
    deal_type: str
    rooms: list[str] | None = None
    price_min: int | None = None
    price_max: int | None = None
    area_min: float | None = None
    area_max: float | None = None


class PropertyCard(BaseModel):
    id: UUID | str
    external_id: str | None = None
    title: str
    property_type: str
    deal_type: str
    new_or_secondary: str | None = None
    city: str
    district: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    metro_station: str | None = None
    metro_distance_min: int | None = None
    rooms: str | None = None
    total_area: float | None = None
    living_area: float | None = None
    kitchen_area: float | None = None
    floor: int | None = None
    total_floors: int | None = None
    ceiling_height: float | None = None
    price: int
    price_per_sqm: int | None = None
    price_unit: str | None = None
    price_period: str | None = None
    renovation: str | None = None
    balcony: bool | None = None
    parking: str | None = None
    description: str | None = None
    features: list[str] | None = None
    complex_name: str | None = None
    developer: str | None = None
    delivery_date: str | None = None
    status: str = "active"
    photos: list[str] | None = None
    site_url: str | None = None
    manager_name: str | None = None
    manager_phone: str | None = None
    manager_email: str | None = None
    raw_data: dict | None = Field(default=None, exclude=True)
