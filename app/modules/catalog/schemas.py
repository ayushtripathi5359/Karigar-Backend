from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class StoneMediaItem(BaseModel):
    media_id: UUID
    media_type: str
    url: str
    thumbnail_url: str | None = None
    is_primary: bool
    sort_order: int


class StoneSummary(BaseModel):
    id: str
    cert_number: str | None
    shape: str
    carat: Decimal
    color_scale: str | None
    fancy_color: str | None
    clarity: str
    cut: str | None
    price: Decimal | None
    rap_discount: Decimal | None
    value_score: Decimal | None
    supplier_display_name: str


class StoneDetail(StoneSummary):
    stone_id: str = Field(description="Supplier's own stone reference")
    lab: str | None
    polish: str | None
    symmetry: str | None
    price_per_carat: Decimal | None
    rap_price: Decimal | None
    measurements: str | None
    availability: str
    media: list[StoneMediaItem] = []


class StoneListResponse(BaseModel):
    items: list[StoneSummary]
    total: int = Field(description="Count of items returned (not total in DB; pagination is offset/limit)")
