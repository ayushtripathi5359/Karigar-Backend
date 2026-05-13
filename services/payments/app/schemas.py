from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PaymentIntentBody(BaseModel):
    order_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)


class PaymentIntentResponse(BaseModel):
    payment_id: UUID
    provider: str
    provider_payment_id: str | None
    amount_inr: Decimal
    status: str
    created_at: datetime


class PaymentConfirmBody(BaseModel):
    payment_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    outcome: Literal["success", "failure"] = "success"


class PaymentConfirmResponse(BaseModel):
    payment_id: UUID
    status: str
    order_id: UUID
    order_status: str
    finalized_at: datetime
