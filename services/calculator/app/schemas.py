from decimal import Decimal
from pydantic import BaseModel, Field


class DiamondPriceLookupRequest(BaseModel):
    item_type:      str = Field(min_length=1)
    batch:          str = Field(min_length=1)
    shape:          str = Field(min_length=1)
    karigar_color:  str = Field(min_length=1)
    karigar_purity: str = Field(min_length=1)
    sieve_size:     str | None = None


class DiamondPriceLookupResponse(BaseModel):
    karigar_price:    int
    vendor_price:     int | None
    vendor_name:      str | None
    avg_weight_carat: Decimal | None
    mm_size:          str | None
    company_grade:    str | None


class MetalRateResponse(BaseModel):
    metal_type:    str
    purity_kt:     int
    colour:        str
    price_per_gram: Decimal


class QuoteRequest(BaseModel):
    # Diamond selection
    item_type:          str
    batch:              str
    shape:              str
    karigar_color:      str
    karigar_purity:     str
    sieve_size:         str | None = None
    total_carat_weight: Decimal = Field(gt=0)

    # Gold selection
    gold_weight_grams: Decimal = Field(gt=0)
    gold_purity_kt:    int     = Field(default=18)
    gold_colour:       str     = Field(default="Yellow")

    # Optional overrides
    making_charges: Decimal | None = Field(default=None, ge=0)
    discount_pct:   Decimal        = Field(default=Decimal("0"), ge=0, le=100)


class QuoteResponse(BaseModel):
    diamond_price_per_carat:   int
    diamond_value:             Decimal
    gold_rate_per_gram:        Decimal
    gold_value:                Decimal
    making_charges:            Decimal
    subtotal:                  Decimal
    markup_amount:             Decimal
    after_markup:              Decimal
    gst_amount:                Decimal
    final_price:               Decimal
    discount_amount:           Decimal
    final_price_after_discount: Decimal


class DropdownOptionsResponse(BaseModel):
    item_types:      list[str]
    batches:         list[str]
    shapes:          list[str]
    karigar_colors:  list[str]
    karigar_purities: list[str]
    sieve_sizes:     list[str]
