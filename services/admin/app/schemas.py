from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AdminSupplierSummary(BaseModel):
    supplier_id: UUID
    supplier_code: str
    display_name: str
    contact_email: str | None = None
    contact_phone: str | None = None
    tier: str | None = None
    is_active: bool | None = None
    role_in_supplier: str | None = None
    is_primary: bool | None = None


class AdminMeResponse(BaseModel):
    user_id: UUID
    role: str
    permissions: list[str]
    suppliers: list[AdminSupplierSummary]


class AdminDashboardResponse(BaseModel):
    users_total: int
    suppliers_active: int
    stones_active: int
    uploads_recent: int
    upload_rows_failed_recent: int


class AdminUserResponse(BaseModel):
    user_id: UUID
    email: str | None
    phone: str | None
    full_name: str | None
    role: str
    is_verified: bool
    created_at: datetime
    last_login_at: datetime | None
    deleted_at: datetime | None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]


class AdminUserUpdateBody(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(buyer|supplier|admin|karigar_staff)$")
    is_verified: bool | None = None
    deleted: bool | None = None


class AdminSupplierListResponse(BaseModel):
    items: list[AdminSupplierSummary]


class AdminSupplierCreateBody(BaseModel):
    supplier_code: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    contact_email: str | None = Field(default=None, max_length=512)
    contact_phone: str | None = Field(default=None, max_length=64)
    tier: str | None = Field(default=None, pattern=r"^(T1|T2|T3)$")
    is_active: bool = True


class AdminSupplierUpdateBody(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=256)
    contact_email: str | None = Field(default=None, max_length=512)
    contact_phone: str | None = Field(default=None, max_length=64)
    tier: str | None = Field(default=None, pattern=r"^(T1|T2|T3)$")
    is_active: bool | None = None


class SupplierUserMappingCreateBody(BaseModel):
    user_id: UUID
    supplier_id: UUID
    role_in_supplier: str = Field(pattern=r"^(owner|manager|viewer)$")
    is_primary: bool = False


class SupplierUserMappingResponse(BaseModel):
    mapping_id: UUID
    user_id: UUID
    supplier_id: UUID
    role_in_supplier: str
    is_primary: bool
    created_by: UUID | None
    created_at: datetime
    deleted_at: datetime | None


class SupplierUserMappingListResponse(BaseModel):
    items: list[SupplierUserMappingResponse]
