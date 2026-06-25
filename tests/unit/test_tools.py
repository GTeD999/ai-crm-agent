from datetime import datetime, timezone
from uuid import uuid4

from app.db.models import User
from app.db.repositories.events import InMemoryEventsRepository
from app.db.repositories.followups import InMemoryFollowupsRepository
from app.db.repositories.leads import InMemoryLeadsRepository
from app.db.repositories.properties import InMemoryPropertiesRepository
from app.db.repositories.users import InMemoryUsersRepository
from app.db.repositories.viewings import InMemoryViewingsRepository
from app.services.ai.tools import ToolsDispatcher
from app.services.properties.models import PropertyCard
from app.services.properties.search import PropertySearchService


def make_user(pd_consent: bool = False) -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        telegram_id=1,
        first_name="Богдан",
        pd_consent=pd_consent,
        created_at=now,
        updated_at=now,
        last_message_at=now,
    )


async def test_save_lead_requires_consent_for_phone() -> None:
    dispatcher = ToolsDispatcher(
        users=InMemoryUsersRepository(),
        leads=InMemoryLeadsRepository(),
        events=InMemoryEventsRepository(),
    )
    result = await dispatcher.dispatch(
        "save_lead",
        {"phone": "+79991234567", "property_type": "house", "deal_type": "buy"},
        make_user(pd_consent=False),
    )

    assert result["ok"] is False
    assert result["error"] == "pd_consent_required"


async def test_confirm_consent_allows_next_tool_in_same_context() -> None:
    user = make_user(pd_consent=False)
    dispatcher = ToolsDispatcher(
        users=InMemoryUsersRepository(),
        leads=InMemoryLeadsRepository(),
        events=InMemoryEventsRepository(),
    )

    await dispatcher.dispatch("confirm_pd_consent", {}, user)
    result = await dispatcher.dispatch(
        "save_lead",
        {"phone": "+79991234567", "property_type": "house", "deal_type": "buy"},
        user,
    )

    assert result["ok"] is True


async def test_search_properties_tool_filters_kind() -> None:
    dispatcher = ToolsDispatcher(
        property_search=PropertySearchService(
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
    )
    result = await dispatcher.dispatch(
        "search_properties",
        {"deal_type": "buy", "property_type": "house", "city": "Новосибирск"},
        make_user(),
    )

    assert result["ok"] is True
    assert len(result["properties"]) == 1
    assert result["properties"][0]["property_type"] == "house"

