"""ORM mappings for user_flow_tracking + trend_signals. SCAFFOLD.

Note: `user_flow_tracking` here is the v2 STONE-INTERACTION table (view, search,
wishlist, etc.) — NOT the auth-event table from v1. Auth events live in
`auth_events` under modules/auth.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserFlowEvent(Base):
    __tablename__ = "user_flow_tracking"

    track_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    stone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_master.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    search_query: Mapped[str | None] = mapped_column(String, nullable=True)
    filter_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    dwell_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_type: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrendSignal(Base):
    __tablename__ = "trend_signals"

    trend_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    kind: Mapped[str] = mapped_column(String, nullable=False)
    period: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    score: Mapped[float | None] = mapped_column(nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
