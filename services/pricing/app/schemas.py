from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class PricingSettingsResponse(BaseModel):
    labour_per_gram: Decimal
    markup: Decimal
    gst: Decimal


class PricingDropdownOptionsResponse(BaseModel):
    item_names: list[str]
    batches: list[str]
    colours: list[str]
    clarities: list[str]
    shapes: list[str]
    sieve_sizes: list[str]


class KarigarPriceLookupRequest(BaseModel):
    item_name: str = Field(min_length=1)
    batch: str = Field(min_length=1)
    colour: str = Field(min_length=1)
    clarity: str = Field(min_length=1)
    shape: str = Field(min_length=1)
    sieve_size: str = Field(min_length=1)


class KarigarPriceLookupResponse(BaseModel):
    karigar_price: Decimal
    vendor_price: Decimal
    vendor_name: str
    carat_weight: Decimal | None = None
    mm_size: str | None = None
    company_grade: str | None = None


class LookupDebugRow(BaseModel):
    item_name: str
    batch: str
    karigar_colour: str
    karigar_purity: str
    shape: str
    sieve_size: str
    karigar_price: Decimal
    vendor_price: Decimal
    vendor_name: str


class LookupDebugResponse(BaseModel):
    normalized_key: dict[str, str]
    lookup_index_size: int
    item_name_sample_rows: list[LookupDebugRow]


class JewelleryQuotationRequest(BaseModel):
    gold_weight: Decimal = Field(gt=0)
    gold_rate: Decimal = Field(gt=0)
    diamond_value: Decimal | None = Field(default=None, ge=0)
    karigar_price_per_carat: Decimal | None = Field(default=None, ge=0)
    total_carat_weight: Decimal | None = Field(default=None, ge=0)
    labour_per_gram: Decimal | None = Field(default=None, ge=0)
    markup: Decimal | None = Field(default=None, ge=0)
    gst: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_diamond_inputs(self) -> "JewelleryQuotationRequest":
        if self.diamond_value is not None and self.karigar_price_per_carat is not None:
            raise ValueError(
                "Provide either diamond_value or karigar_price_per_carat, not both."
            )
        return self


class JewelleryQuotationResponse(BaseModel):
    gold_value: Decimal
    labour: Decimal
    diamond_value: Decimal
    subtotal: Decimal
    after_markup: Decimal
    final_price: Decimal
