from app.db.repositories.properties import InMemoryPropertiesRepository
from app.services.properties.models import PropertyCard, PropertySearchArgs
from app.services.properties.search import PropertySearchService


async def test_property_search_does_not_mix_house_with_apartment() -> None:
    service = PropertySearchService(
        InMemoryPropertiesRepository(
            [
                PropertyCard(
                    id="1",
                    title="Квартира",
                    property_type="apartment",
                    deal_type="buy",
                    city="Новосибирск",
                    price=5_000_000,
                ),
                PropertyCard(
                    id="2",
                    title="Дом",
                    property_type="house",
                    deal_type="buy",
                    city="Новосибирск",
                    price=50_000_000,
                ),
            ]
        )
    )

    result = await service.search_properties(
        PropertySearchArgs(deal_type="buy", property_type="house", city="Новосибирск")
    )

    assert len(result) == 1
    assert result[0].property_type == "house"


async def test_property_search_ranks_by_query_text_before_price() -> None:
    service = PropertySearchService(
        InMemoryPropertiesRepository(
            [
                PropertyCard(
                    id="1",
                    title="Офис у метро",
                    property_type="commercial",
                    deal_type="rent",
                    city="Новосибирск",
                    district="Центральный",
                    total_area=80,
                    price=100_000,
                    description="Офисное помещение с ремонтом",
                ),
                PropertyCard(
                    id="2",
                    title="Теплый склад",
                    property_type="commercial",
                    deal_type="rent",
                    city="Новосибирск",
                    district="Кировский",
                    total_area=260,
                    price=180_000,
                    description="Складское помещение для производства, отдельный вход, подъезд для грузового транспорта",
                ),
            ]
        )
    )

    result = await service.search_properties(
        PropertySearchArgs(
            deal_type="rent",
            property_type="commercial",
            city="Новосибирск",
            query_text="нужен теплый склад под производство 200-300 м2",
            area_min=200,
            area_max=300,
        )
    )

    assert result[0].id == "2"


async def test_property_search_prefers_objects_closer_to_large_budget() -> None:
    service = PropertySearchService(
        InMemoryPropertiesRepository(
            [
                PropertyCard(
                    id="cheap",
                    title="Коммерческое помещение для инвестиций",
                    property_type="commercial",
                    deal_type="buy",
                    city="Новосибирск",
                    price=20_000_000,
                    description="Коммерческая недвижимость для инвестиций, отдельный вход",
                ),
                PropertyCard(
                    id="near-budget",
                    title="Большой коммерческий объект для инвестиций",
                    property_type="commercial",
                    deal_type="buy",
                    city="Новосибирск",
                    price=92_000_000,
                    description="Коммерческая недвижимость для инвестиций, арендный потенциал",
                ),
            ]
        )
    )

    result = await service.search_properties(
        PropertySearchArgs(
            deal_type="buy",
            property_type="commercial",
            city="Новосибирск",
            query_text="коммерческая недвижимость для инвестиций",
            price_max=100_000_000,
        )
    )

    assert result[0].id == "near-budget"


async def test_property_search_does_not_let_budget_floor_lose_to_keyword_stuffing() -> None:
    service = PropertySearchService(
        InMemoryPropertiesRepository(
            [
                PropertyCard(
                    id="too-low",
                    title="Коммерческая недвижимость для инвестиций",
                    property_type="commercial",
                    deal_type="buy",
                    city="Новосибирск",
                    price=21_500_000,
                    description=(
                        "Коммерческая недвижимость для инвестиций, готовый арендный бизнес, "
                        "отдельный вход, окупаемость, трафик, арендаторы"
                    ),
                ),
                PropertyCard(
                    id="closer",
                    title="Коммерческий объект",
                    property_type="commercial",
                    deal_type="buy",
                    city="Новосибирск",
                    price=86_000_000,
                    description="Подходит для покупки в высокий бюджет.",
                ),
            ]
        )
    )

    result = await service.search_properties(
        PropertySearchArgs(
            deal_type="buy",
            property_type="commercial",
            city="Новосибирск",
            query_text="коммерческая недвижимость для инвестиций готовый арендный бизнес",
            price_max=100_000_000,
        )
    )

    assert result[0].id == "closer"


async def test_property_search_prefers_pricier_available_apartment_when_budget_is_high() -> None:
    service = PropertySearchService(
        InMemoryPropertiesRepository(
            [
                PropertyCard(
                    id="small",
                    title="Квартира 56 м²",
                    property_type="apartment",
                    deal_type="buy",
                    city="Новосибирск",
                    price=5_200_000,
                    description="Квартира с хорошим описанием, ремонт, район, рядом остановка, подходит под бюджет.",
                ),
                PropertyCard(
                    id="large",
                    title="Квартира 114 м²",
                    property_type="apartment",
                    deal_type="buy",
                    city="Новосибирск",
                    price=15_000_000,
                    description="Просторная квартира.",
                ),
            ]
        )
    )

    result = await service.search_properties(
        PropertySearchArgs(
            deal_type="buy",
            property_type="apartment",
            city="Новосибирск",
            query_text="квартиры в этом бюджете",
            price_max=100_000_000,
        )
    )

    assert result[0].id == "large"

