from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.users.schemas import AddressCreateBody


class OrderCreateBody(BaseModel):
    stone_id: UUID
    quantity: int = Field(default=1, ge=1, le=1)            # diamonds are unique — clamp to 1
    address_id: UUID | None = None
    new_address: AddressCreateBody | None = None            # capture inline if provided
    notes: str | None = Field(default=None, max_length=512)


class OrderItemResponse(BaseModel):
    order_item_id: UUID
    stone_id: UUID
    quantity: int
    unit_price_inr: Decimal
    total_price_inr: Decimal


class OrderTrackingEvent(BaseModel):
    status: str
    notes: str | None
    event_at: datetime


class OrderSummary(BaseModel):
    order_id: UUID
    status: str
    total_inr: Decimal
    created_at: datetime
    item_count: int


class OrderListResponse(BaseModel):
    items: list[OrderSummary]


class OrderDetailResponse(BaseModel):
    order_id: UUID
    buyer_id: UUID
    status: str
    subtotal_inr: Decimal
    discount_inr: Decimal
    tax_inr: Decimal
    total_inr: Decimal
    billing_address_id: UUID | None
    shipping_address_id: UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]
    tracking: list[OrderTrackingEvent]
