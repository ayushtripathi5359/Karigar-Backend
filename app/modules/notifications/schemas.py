from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


NotificationType = str


class NotificationResponse(BaseModel):
    notification_id: UUID
    user_id: UUID
    type: NotificationType
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

