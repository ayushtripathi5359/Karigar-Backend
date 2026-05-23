from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    notification_id: UUID
    user_id: UUID
    type: str
    title: str
    body: str | None = None
    metadata: dict | None = None
    is_read: bool
    read_at: datetime | None = None
    news_id: UUID | None = None
    order_id: UUID | None = None
    stone_id: UUID | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class PushTokenRegisterBody(BaseModel):
    push_token: str = Field(min_length=1, max_length=2048)
    provider: str = Field(default="expo", pattern=r"^(expo|stub)$")
    platform: str | None = Field(default=None, max_length=64)
    device_id: str | None = Field(default=None, max_length=256)
    app_version: str | None = Field(default=None, max_length=64)


class PushTokenResponse(BaseModel):
    token_id: UUID
    provider: str
    push_token: str
    platform: str | None
    device_id: str | None
    app_version: str | None
    is_active: bool
    last_seen_at: datetime


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


class NotificationDispatchResponse(BaseModel):
    sent: int
    failed: int
    skipped: int = 0


class AdminTestPushBody(BaseModel):
    title: str = Field(default="Karigar test notification", min_length=1, max_length=180)
    body: str | None = Field(default="Push delivery check from admin.", max_length=1200)
