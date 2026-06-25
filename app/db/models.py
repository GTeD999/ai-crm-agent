from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class LeadStatus(str, Enum):
    NEW = "new"
    QUALIFIED = "qualified"
    HOT = "hot"
    TRANSFERRED = "transferred"
    COLD = "cold"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    telegram_id: int
    telegram_username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    pd_consent: bool = False
    pd_consent_at: datetime | None = None
    is_silent: bool = False
    silent_since: datetime | None = None
    context_summary: str | None = None
    summary_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class UserCreate(BaseModel):
    telegram_id: int
    telegram_username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    role: MessageRole
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    intent: str | None = None
    sentiment: str | None = None
    urgency: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    model: str | None = None
    created_at: datetime


class MessageCreate(BaseModel):
    user_id: UUID
    role: MessageRole
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    intent: str | None = None
    sentiment: str | None = None
    urgency: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    model: str | None = None


class LeadData(BaseModel):
    property_type: str | None = None
    deal_type: str | None = None
    rooms: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    area_min: float | None = None
    area_max: float | None = None
    districts: list[str] = Field(default_factory=list)
    city: str | None = None
    purpose: str | None = None
    timeline: str | None = None
    mortgage_needed: bool | None = None
    additional_notes: str | None = None
    score: int = 0
    status: LeadStatus = LeadStatus.NEW


class Lead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    property_type: str | None = None
    deal_type: str | None = None
    new_or_secondary: str | None = None
    rooms: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    area_min: float | None = None
    area_max: float | None = None
    districts: list[str] | None = None
    city: str | None = None
    purpose: str | None = None
    timeline: str | None = None
    mortgage_needed: bool | None = None
    has_first_payment: bool | None = None
    first_payment_amount: int | None = None
    selling_other_property: bool | None = None
    materinsky_capital: bool | None = None
    additional_notes: str | None = None
    score: int = 0
    status: LeadStatus = LeadStatus.NEW
    bitrix_lead_id: int | None = None
    bitrix_deal_id: int | None = None
    transferred_to_manager_at: datetime | None = None
    transfer_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class LeadUpdate(BaseModel):
    property_type: str | None = None
    deal_type: str | None = None
    new_or_secondary: str | None = None
    rooms: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    area_min: float | None = None
    area_max: float | None = None
    districts: list[str] | None = None
    city: str | None = None
    purpose: str | None = None
    timeline: str | None = None
    mortgage_needed: bool | None = None
    has_first_payment: bool | None = None
    first_payment_amount: int | None = None
    selling_other_property: bool | None = None
    materinsky_capital: bool | None = None
    additional_notes: str | None = None
    score: int | None = None
    status: LeadStatus | None = None
    bitrix_lead_id: int | None = None
    bitrix_deal_id: int | None = None
    transfer_reason: str | None = None


class Event(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    event_type: str
    event_data: dict | None = None
    created_at: datetime


class EventCreate(BaseModel):
    user_id: UUID | None = None
    event_type: str
    event_data: dict | None = None


class Viewing(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    property_id: str
    scheduled_at: datetime
    duration_min: int = 30
    status: str = "scheduled"
    manager_id: str | None = None
    client_phone: str | None = None
    notes: str | None = None
    bitrix_event_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ViewingCreate(BaseModel):
    user_id: UUID
    property_id: str
    scheduled_at: datetime
    client_phone: str
    notes: str | None = None


class Followup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    lead_id: UUID | None = None
    step: int
    scheduled_at: datetime
    sent_at: datetime | None = None
    status: str = "pending"
    message: str | None = None
    response_received: bool = False
    created_at: datetime


class FollowupCreate(BaseModel):
    user_id: UUID
    lead_id: UUID | None = None
    step: int
    scheduled_at: datetime
    message: str | None = None
