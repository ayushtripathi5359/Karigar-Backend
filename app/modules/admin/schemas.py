from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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
    admin_unread_notifications: int = 0
    open_demands: int = 0
    failed_push_deliveries: int = 0
    recent_campaigns: int = 0


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


class NotificationCampaignCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    body: str | None = Field(default=None, max_length=1200)
    image_url: str | None = Field(default=None, max_length=2048)
    deep_link: str | None = Field(default=None, max_length=1024)
    target_role: str = Field(default="buyer", pattern=r"^(all|buyer|supplier|admin|karigar_staff)$")
    target_supplier_id: UUID | None = None


class NotificationCampaignResponse(BaseModel):
    campaign_id: UUID
    created_by: UUID | None
    title: str
    body: str | None
    image_url: str | None
    deep_link: str | None
    target_role: str
    target_supplier_id: UUID | None
    status: str
    published_at: datetime | None
    created_at: datetime


class NotificationCampaignListResponse(BaseModel):
    items: list[NotificationCampaignResponse]


class NotificationOutboxResponse(BaseModel):
    outbox_id: UUID
    notification_id: UUID
    channel: str
    status: str
    attempt_count: int
    last_error: str | None
    provider_message_id: str | None
    created_at: datetime
    delivered_at: datetime | None


class NotificationOutboxListResponse(BaseModel):
    items: list[NotificationOutboxResponse]


class AdminDemandRequestUpdateBody(BaseModel):
    status: str = Field(pattern=r"^(open|countered|accepted|rejected|cancelled)$")
    response_note: str | None = Field(default=None, max_length=1000)
    offered_price_inr: Decimal | None = Field(default=None, ge=0)


class AdminDemandRequestResponse(BaseModel):
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
    resolved_at: datetime | None


class AdminDemandRequestListResponse(BaseModel):
    items: list[AdminDemandRequestResponse]


class AdminTestPushBody(BaseModel):
    title: str = Field(default="Karigar test notification", min_length=1, max_length=180)
    body: str | None = Field(default="Push delivery check from admin.", max_length=1200)
