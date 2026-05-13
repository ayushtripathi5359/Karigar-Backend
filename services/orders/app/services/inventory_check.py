"""Stone availability check against the shared supplier_master table."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def assert_available(session: AsyncSession, stone_id: uuid.UUID) -> None:
    row = (
        await session.execute(
            text(
                """
                SELECT availability, deleted_at
                FROM supplier_master
                WHERE id = :id
                """
            ),
            {"id": str(stone_id)},
        )
    ).first()

    if row is None or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stone not found")
    if row.availability != "available":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"stone is {row.availability} — not available for purchase",
        )
