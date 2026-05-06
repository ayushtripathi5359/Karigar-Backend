"""ORM mappings for supplier_master + stone_media. SCAFFOLD — minimal columns
exposed; extend as endpoints land. Full column list lives in the schema."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SupplierMaster(Base):
    __tablename__ = "supplier_master"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id"), nullable=False)
    stone_id: Mapped[str] = mapped_column(String, nullable=False)
    cert_number: Mapped[str | None] = mapped_column(String, nullable=True)
    shape: Mapped[str] = mapped_column(String, nullable=False)
    carat: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    color_scale: Mapped[str | None] = mapped_column(String, nullable=True)
    fancy_color: Mapped[str | None] = mapped_column(String, nullable=True)
    clarity: Mapped[str] = mapped_column(String, nullable=False)
    cut: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    availability: Mapped[str] = mapped_column(String, nullable=False, default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StoneMedia(Base):
    __tablename__ = "stone_media"

    media_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    stone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_master.id"), nullable=False)
    media_type: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
