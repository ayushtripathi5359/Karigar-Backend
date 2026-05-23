from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class DemandRequestCreateBody(BaseModel):
    stone_id: UUID
    requested_discount_pct: Decimal | None = Field(default=None, ge=0, le=100)
    requested_price_inr: Decimal | None = Field(default=None, ge=0)
    message: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_amount(self) -> "DemandRequestCreateBody":
        if self.requested_discount_pct is None and self.requested_price_inr is None:
            raise ValueError("requested_discount_pct or requested_price_inr is required")
        return self


class DemandRequestUpdateBody(BaseModel):
    status: str = Field(pattern=r"^(open|countered|accepted|rejected|cancelled)$")
    response_note: str | None = Field(default=None, max_length=1000)
    offered_price_inr: Decimal | None = Field(default=None, ge=0)


class DemandRequestResponse(BaseModel):
    demand_request_id: UUID
    buyer_id: UUID
    stone_id: UUID
    supplier_id: UUID
    supplier_display_name: str | None = None
    stone_code: str | None = None
    requested_discount_pct: Decimal | None = None
    requested_price_inr: Decimal | None = None
    message: str | None = None
    status: str
    response_note: str | None = None
    offered_price_inr: Decimal | None = None
    resolved_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class DemandRequestListResponse(BaseModel):
    items: list[DemandRequestResponse]
