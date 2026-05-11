"""ORM mappings for suppliers, supplier_uploads, scrape_jobs."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from karigar_shared.db.base import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupplierUpload(Base):
    __tablename__ = "supplier_uploads"

    upload_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.supplier_id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trending_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_log: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
