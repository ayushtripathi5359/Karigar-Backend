"""order_tracking + inventory_log writers."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


async def log_status(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    status: str,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO order_tracking (order_id, status, notes, created_by)
            VALUES (:o, CAST(:s AS order_status), :n, :a)
            """
        ),
        {"o": str(order_id), "s": status, "n": notes,
         "a": str(actor_user_id) if actor_user_id else None},
    )


async def record_purchase(
    session: AsyncSession,
    *,
    stone_id: uuid.UUID,
    user_id: uuid.UUID,
    price_inr: Decimal,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO inventory_log (
                stone_id, event_type, user_id, quantity_change, price_inr
            ) VALUES (
                :s, CAST('purchased' AS inventory_event_type), :u, -1, :p
            )
            """
        ),
        {"s": str(stone_id), "u": str(user_id), "p": price_inr},
    )
