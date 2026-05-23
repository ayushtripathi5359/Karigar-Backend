from __future__ import annotations

from datetime import datetime
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
