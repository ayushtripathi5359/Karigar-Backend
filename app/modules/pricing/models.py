"""ORM mappings for rapaport_price_mapping, value_scores, price_history. SCAFFOLD."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RapaportPrice(Base):
    __tablename__ = "rapaport_price_mapping"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    shape: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False)
    clarity: Mapped[str] = mapped_column(String, nullable=False)
    carat_from: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    carat_to: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    rap_price_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    usd_to_inr_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ValueScore(Base):
    __tablename__ = "value_scores"

    score_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    stone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_master.id", ondelete="CASCADE"), nullable=False)
    carat_factor: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    color_factor: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    clarity_factor: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    cut_factor: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    liquidity_factor: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    formula_version: Mapped[str] = mapped_column(String, nullable=False, default="v1.0")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
