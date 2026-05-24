from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class SupplierResponse(BaseModel):
    supplier_id: UUID
    supplier_code: str | None = None
    display_name: str
    contact_email: str | None = None
    contact_phone: str | None = None
    tier: str | None = None
    is_active: bool


class SupplierUploadCreateBody(BaseModel):
    supplier_id: UUID
    file_url: str | None = Field(default=None, max_length=2048)


class SupplierUploadResponse(BaseModel):
    upload_id: UUID
    supplier_id: UUID
    supplier_display_name: str | None = None
    file_url: str | None = None
    file_type: str
    status: str
    rows_total: int | None = None
    rows_imported: int | None = None
    rows_new: int | None = None
    rows_updated: int | None = None
    rows_failed: int | None = None
    rows_trending: int | None = None
    error_log: list[dict] | dict | None = None
    uploaded_by: UUID | None = None
    uploaded_at: datetime
    processed_at: datetime | None = None


class SupplierUploadListResponse(BaseModel):
    items: list[SupplierUploadResponse]


class SupplierUploadCreateResponse(BaseModel):
    upload: SupplierUploadResponse


class SupplierInventoryResponse(BaseModel):
    id: UUID
    supplier_id: UUID
    supplier_display_name: str | None = None
    stone_id: str
    cert_number: str | None = None
    lab: str | None = None
    availability: str
    shape: str
    carat: Decimal
    color_scale: str | None = None
    fancy_color: str | None = None
    clarity: str
    cut: str | None = None
    polish: str | None = None
    symmetry: str | None = None
    price_per_carat: Decimal | None = None
    price: Decimal | None = None
    rap_price: Decimal | None = None
    rap_discount: Decimal | None = None
    measurements: str | None = None
    supplier_extras: dict | None = None
    updated_at: datetime


class SupplierInventoryListResponse(BaseModel):
    items: list[SupplierInventoryResponse]


class SupplierInventoryUpdateBody(BaseModel):
    shape: str | None = Field(default=None, pattern=r"^(round|princess|cushion|oval|emerald|pear|marquise|radiant|asscher|heart|other)$")
    carat: Decimal | None = Field(default=None, gt=0)
    color_scale: str | None = Field(default=None, pattern=r"^[D-Z]$")
    fancy_color: str | None = Field(default=None, max_length=128)
    clarity: str | None = Field(default=None, pattern=r"^(FL|IF|VVS1|VVS2|VS1|VS2|SI1|SI2|I1|I2|I3)$")
    cut: str | None = Field(default=None, pattern=r"^(Excellent|Very Good|Good|Fair|Poor)$")
    polish: str | None = Field(default=None, pattern=r"^(Excellent|Very Good|Good|Fair|Poor)$")
    symmetry: str | None = Field(default=None, pattern=r"^(Excellent|Very Good|Good|Fair|Poor)$")
    cert_number: str | None = Field(default=None, max_length=128)
    lab: str | None = Field(default=None, pattern=r"^(GIA|IGI|HRD|AGS|GCAL|GSI|other)$")
    price: Decimal | None = Field(default=None, ge=0)
    price_per_carat: Decimal | None = Field(default=None, ge=0)
    rap_price: Decimal | None = Field(default=None, ge=0)
    rap_discount: Decimal | None = Field(default=None, ge=-1, le=1)
    availability: str | None = Field(default=None, pattern=r"^(available|on_hold|sold|memo|withdrawn)$")
    measurements: str | None = Field(default=None, max_length=128)
    supplier_extras: dict | None = None
